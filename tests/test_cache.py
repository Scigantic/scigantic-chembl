from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

import scigantic_chembl as chembl
from scigantic_chembl import cache
from scigantic_chembl.cache import resolve

# A tiny, known-small file, chosen so these tests exercise the real
# download/reuse mechanism without pulling a multi-hundred-MB parquet file
# just to prove caching works at all.
_SMALL_KEY = "_MANIFEST.json"


def test_disabled_by_default_returns_s3_url():
    assert chembl.is_cache_enabled() is False
    assert resolve(_SMALL_KEY) == f"s3://scigantic-chembl/{_SMALL_KEY}"


def test_enable_cache_downloads_and_reuses(tmp_path):
    resolved_dir = chembl.enable_cache(cache_dir=str(tmp_path))
    try:
        assert chembl.is_cache_enabled() is True
        assert resolved_dir == tmp_path
        assert chembl.cache_dir() == tmp_path

        local_path = resolve(_SMALL_KEY)
        assert local_path == str(tmp_path / _SMALL_KEY)
        assert (tmp_path / _SMALL_KEY).exists()
        assert (tmp_path / _SMALL_KEY).stat().st_size > 0
        # No leftover partial-download artifact.
        assert list(tmp_path.glob(f"{_SMALL_KEY}.*.part")) == []

        mtime_first = (tmp_path / _SMALL_KEY).stat().st_mtime
        second_path = resolve(_SMALL_KEY)
        assert second_path == local_path
        # Same mtime proves the second call reused the file rather than
        # re-downloading it.
        assert (tmp_path / _SMALL_KEY).stat().st_mtime == mtime_first
    finally:
        chembl.disable_cache()


def test_disable_cache_reverts_to_s3(tmp_path):
    chembl.enable_cache(cache_dir=str(tmp_path))
    chembl.disable_cache()
    assert chembl.is_cache_enabled() is False
    assert resolve(_SMALL_KEY) == f"s3://scigantic-chembl/{_SMALL_KEY}"


def test_interrupted_download_leaves_no_corrupt_final_file(tmp_path):
    # A killed download must never leave something at the real path that
    # looks cached but isn't. Simulates a network drop partway through a
    # read, then confirms a real, unmocked retry recovers cleanly.
    class DroppedConnection:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self, _n):
            if getattr(self, "_served", False):
                raise ConnectionError("simulated network drop mid-download")
            self._served = True
            return b"partial-bytes"

    chembl.enable_cache(cache_dir=str(tmp_path))
    try:
        with mock.patch("urllib.request.urlopen", return_value=DroppedConnection()):
            with pytest.raises(ConnectionError):
                resolve(_SMALL_KEY)

        final = tmp_path / _SMALL_KEY
        parts = list(tmp_path.glob(f"{_SMALL_KEY}.*.part"))
        assert not final.exists()
        assert len(parts) == 1  # harmless debris, not corruption

        # Real retry, no mocking: must succeed. It leaves its own new temp
        # file rather than reusing the dropped one (each call's temp name
        # is unique), so the recovered download is checked by name, and the
        # stale leftover from the dropped attempt is a separate assertion.
        recovered = resolve(_SMALL_KEY)
        assert final.exists()
        assert final.stat().st_size > 0
        assert recovered == str(final)
    finally:
        chembl.disable_cache()


def test_concurrent_downloads_of_the_same_key_never_raise(tmp_path):
    # Regression test for a real bug: the temp filename used to be
    # deterministic (derived only from the cache key), so two threads
    # racing to fill the *same* key shared one temp path. Whichever
    # thread's os.replace() ran second raised FileNotFoundError, because
    # the first had already consumed it.
    #
    # Exercised against cache._atomic_download() directly with a real
    # local file:// URL rather than mock.patch("urllib.request.urlopen"):
    # mock.patch mutates a single shared module attribute, so 16 threads
    # each entering/exiting their own patch on the same target race each
    # other's save/restore and corrupt one another's mock, independent of
    # anything being tested here. A real urlopen() against a local file is
    # just as fast and has no such hazard.
    source = tmp_path / "source.bin"
    body = b"cached-body"
    source.write_bytes(body)
    source_url = source.as_uri()

    local_path = tmp_path / "cached" / "key.parquet"
    local_path.parent.mkdir()
    errors = []

    def download(_i):
        try:
            cache._atomic_download(source_url, local_path)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(download, range(16)))

    assert errors == []
    assert local_path.exists()
    assert local_path.read_bytes() == body
    assert list(local_path.parent.glob("key.parquet.*.part")) == []


def test_concurrent_first_resolve_of_the_same_key_downloads_once(tmp_path):
    # Regression test for a real inefficiency: resolve()'s check-then-
    # download wasn't coordinated across threads, so N threads racing the
    # first resolve() of a key each saw it missing and each downloaded it
    # in full. Verified directly before this was fixed with a per-key
    # lock: 16 threads calling resolve() concurrently on an empty cache
    # triggered 16 separate downloads of the same file instead of one.
    #
    # mock.patch is entered/exited only once here, by the main thread,
    # before the pool starts; the worker threads only read the already-
    # patched attribute, so this doesn't hit the same-target mock.patch
    # race that test_concurrent_downloads_of_the_same_key_never_raise's
    # docstring describes for patching from multiple threads at once.
    body = b"cached-body"

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self, *_args):
            if getattr(self, "_served", False):
                return b""
            self._served = True
            return body

    chembl.enable_cache(cache_dir=str(tmp_path))
    try:
        with mock.patch(
            "urllib.request.urlopen", side_effect=lambda *a, **k: FakeConnection()
        ) as urlopen:
            with ThreadPoolExecutor(max_workers=16) as pool:
                paths = list(pool.map(lambda _i: resolve("shared/once.parquet"), range(16)))

        assert len(set(paths)) == 1
        assert urlopen.call_count == 1  # only one thread actually downloaded
        final = tmp_path / "shared" / "once.parquet"
        assert final.read_bytes() == body
    finally:
        chembl.disable_cache()


def test_cached_activities_match_uncached(tmp_path):
    # The one integration-level check: caching actually gets used by a
    # real function, not just by resolve() directly, and returns the same
    # data. Uses activities_enriched.parquet, the smallest of the three
    # derived artifacts (190 MB), rather than the two ~460 MB fingerprint
    # files, since this test pays for a real download.
    uncached = chembl.activities(target_chembl_id="CHEMBL203")

    chembl.enable_cache(cache_dir=str(tmp_path))
    try:
        cached = chembl.activities(target_chembl_id="CHEMBL203")
        cached_file = tmp_path / "chembl_37" / "derived" / "activities_enriched.parquet"
        assert cached_file.exists()
    finally:
        chembl.disable_cache()

    assert len(cached) == len(uncached)
    assert sorted(cached["compound_chembl_id"]) == sorted(uncached["compound_chembl_id"])
