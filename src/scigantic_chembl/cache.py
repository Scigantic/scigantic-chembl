"""Optional local caching: download once, then work with no network.

Off by default. This package's whole pitch is zero setup, so caching stays
opt-in rather than something that changes the default behavior:

    import scigantic_chembl as chembl
    chembl.enable_cache()

activities(), similar_compounds() and substructure_search() then read from
a local cache directory instead of S3, downloading their one derived file
the first time it's needed and reusing it after that.

connect() / query() deliberately do NOT use this: connect() registers ten
core tables as views on every call, several over 1 GB, so caching them
there would mean any call eagerly downloads everything regardless of what
the query actually touches. Cache a specific table yourself if you want
it locally: cache_resolve("<release>/parquet/<table>.parquet") downloads it
and returns the local path, usable directly in read_parquet(...).
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ._constants import BUCKET, REGION

_enabled = False
_cache_dir: Path | None = None

_CHUNK_BYTES = 1024 * 1024
_TIMEOUT_SECONDS = 5


def _default_cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "scigantic-chembl"


def enable_cache(cache_dir: str | None = None) -> Path:
    """Turn on local caching for every function in this package.

    Cache location: `cache_dir` if given, else the SCIGANTIC_CHEMBL_CACHE
    environment variable, else a platform-appropriate user cache directory
    (~/.cache/scigantic-chembl on Linux, ~/Library/Caches/scigantic-chembl
    on macOS, %LOCALAPPDATA%\\scigantic-chembl on Windows). Returns the
    resolved directory.
    """
    global _enabled, _cache_dir
    if cache_dir is not None:
        resolved = Path(cache_dir)
    elif os.environ.get("SCIGANTIC_CHEMBL_CACHE"):
        resolved = Path(os.environ["SCIGANTIC_CHEMBL_CACHE"])
    else:
        resolved = _default_cache_dir()
    resolved.mkdir(parents=True, exist_ok=True)
    _cache_dir = resolved
    _enabled = True
    return resolved


def disable_cache() -> None:
    """Turn caching back off. Later calls go straight to S3 again.

    Anything already downloaded stays on disk; this only stops using it.
    """
    global _enabled
    _enabled = False


def is_cache_enabled() -> bool:
    return _enabled


def cache_dir() -> Path | None:
    """The resolved cache directory, or None if caching has never been enabled."""
    return _cache_dir


def resolve(key: str) -> str:
    """An S3 URL, or a local cached file path if caching is on.

    `key` is a path relative to the bucket root, e.g.
    "chembl_37/parquet/activities.parquet". Downloads to the cache on
    first access; later calls for the same key reuse the local file
    without touching the network.
    """
    if not _enabled:
        return f"s3://{BUCKET}/{key}"

    assert _cache_dir is not None
    local_path = _cache_dir / key
    if local_path.exists():
        return str(local_path)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}"
    # Download to a sibling temp file and rename into place atomically, so a
    # download killed partway through never leaves a file that looks cached
    # but isn't. Same reasoning as the mirror's own _SCIGANTIC_MIRROR_COMPLETE
    # marker: presence has to mean "this is really, fully here."
    tmp_path = local_path.with_name(local_path.name + ".part")
    print(f"scigantic-chembl: caching {key} ...", file=sys.stderr, flush=True)
    with urllib.request.urlopen(url) as response, open(tmp_path, "wb") as fh:
        while chunk := response.read(_CHUNK_BYTES):
            fh.write(chunk)
    os.replace(tmp_path, local_path)
    return str(local_path)


def _etag(key: str) -> str | None:
    """The current S3 ETag for the object at this key, or None on failure.

    A plain HEAD request regardless of cache state: resolve() above skips
    the network entirely on a cache hit, so it's not a reliable place to
    observe this, and the release string alone only pins a caller to a
    folder, not to the exact bytes at that key. This is what would catch
    an object silently changing underneath an unchanged release.
    """
    url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}"
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            etag = response.headers.get("ETag")
    except (urllib.error.URLError, TimeoutError):
        return None
    return etag.strip('"') if etag else None
