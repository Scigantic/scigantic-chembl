"""Release metadata: what's mirrored, and what each release supports.

Reads a small manifest at s3://scigantic-chembl/_MANIFEST.json, regenerated
on every run of the mirror's release-check cron by probing the bucket
directly. That keeps this package in step with the mirror without needing
a new package release every time the mirror gains a ChEMBL version.

The manifest is fetched once per process and cached. If it can't be
fetched (no network, a bucket hiccup), calls fall back to the snapshot
below rather than failing outright: worst case is that the package is only
as fresh as this package version, not broken.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass

from ._constants import BUCKET, REGION

_MANIFEST_URL = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/_MANIFEST.json"
_TIMEOUT_SECONDS = 5

# Last-known-good snapshot, shipped with this package version. Only used if
# the live manifest can't be fetched.
_FALLBACK_LATEST = "chembl_37"
_FALLBACK_RELEASES = {
    "chembl_37": {
        "raw": True,
        "activities_enriched": True,
        "fingerprints": True,
        "cyp_training": True,
    },
    "chembl_36": {
        "raw": True,
        "activities_enriched": False,
        "fingerprints": False,
        "cyp_training": True,
    },
    "chembl_35": {
        "raw": True,
        "activities_enriched": False,
        "fingerprints": False,
        "cyp_training": True,
    },
}


class UnknownReleaseError(LookupError):
    """Raised when a release isn't mirrored at all."""


class ReleaseCapabilityError(LookupError):
    """Raised when a release doesn't carry the artifact a call asked for."""


@dataclass(frozen=True)
class ReleaseInfo:
    release: str
    raw: bool
    activities_enriched: bool
    fingerprints: bool
    cyp_training: bool


_cache: dict | None = None


def _manifest() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with urllib.request.urlopen(_MANIFEST_URL, timeout=_TIMEOUT_SECONDS) as response:
            _cache = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        # HTTPError (a URLError subclass) carries an open response body; left
        # unclosed it raises its own ResourceWarning on garbage collection,
        # on top of the one we're about to emit deliberately below.
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
        warnings.warn(
            f"could not fetch the live release manifest ({exc!r}); falling back "
            "to the snapshot shipped with this package version, which may be stale",
            stacklevel=3,
        )
        _cache = {"latest": _FALLBACK_LATEST, "releases": _FALLBACK_RELEASES}
    return _cache


def releases() -> list[ReleaseInfo]:
    """List every release the mirror carries, and what each one supports."""
    data = _manifest()
    return [ReleaseInfo(release=name, **caps) for name, caps in data["releases"].items()]


def latest() -> str:
    """The release the archive treats as its current default."""
    return _manifest()["latest"]


def _validate_release(release: str) -> None:
    data = _manifest()
    if release not in data["releases"]:
        known = ", ".join(data["releases"])
        raise UnknownReleaseError(f"{release!r} is not mirrored. Known releases: {known}.")


def _require(release: str, capability: str) -> None:
    _validate_release(release)
    data = _manifest()
    if not data["releases"][release][capability]:
        raise ReleaseCapabilityError(
            f"{release!r} has no {capability.replace('_', ' ')}. Only "
            f"{data['latest']} carries the derived layer today. Call "
            "releases() to see what each release supports, or use query() "
            "against the raw parquet tables instead."
        )
