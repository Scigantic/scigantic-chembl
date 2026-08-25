"""Release metadata: what's mirrored, and what each release supports."""

from __future__ import annotations

from dataclasses import dataclass

from ._constants import DEFAULT_RELEASE, RELEASES


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


def releases() -> list[ReleaseInfo]:
    """List every release the mirror carries, and what each one supports."""
    return [ReleaseInfo(release=name, **caps) for name, caps in RELEASES.items()]


def latest() -> str:
    """The release the archive treats as its current default."""
    return DEFAULT_RELEASE


def _validate_release(release: str) -> None:
    if release not in RELEASES:
        known = ", ".join(RELEASES)
        raise UnknownReleaseError(f"{release!r} is not mirrored. Known releases: {known}.")


def _require(release: str, capability: str) -> None:
    _validate_release(release)
    if not RELEASES[release][capability]:
        raise ReleaseCapabilityError(
            f"{release!r} has no {capability.replace('_', ' ')}. Only "
            f"{DEFAULT_RELEASE} carries the derived layer today. Call "
            "releases() to see what each release supports, or use query() "
            "against the raw parquet tables instead."
        )
