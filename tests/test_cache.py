from unittest import mock

import pytest

import scigantic_chembl as chembl
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
        assert not (tmp_path / (_SMALL_KEY + ".part")).exists()

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
        part = tmp_path / (_SMALL_KEY + ".part")
        assert not final.exists()
        assert part.exists()  # harmless debris, not corruption

        # Real retry, no mocking: must succeed and clean up the leftover.
        recovered = resolve(_SMALL_KEY)
        assert final.exists()
        assert final.stat().st_size > 0
        assert not part.exists()
        assert recovered == str(final)
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
