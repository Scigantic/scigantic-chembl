"""Query ChEMBL directly from a public S3 mirror. No download, no local database."""

from importlib.metadata import PackageNotFoundError, version as _version

from .activities import activities
from .connection import connect, query
from .releases import (
    ReleaseCapabilityError,
    ReleaseInfo,
    UnknownReleaseError,
    latest,
    releases,
)
from .similarity import similar_compounds
from .substructure import substructure_search

try:
    __version__ = _version("scigantic-chembl")
except PackageNotFoundError:
    # Running from a source checkout with no install (editable or not).
    __version__ = "0.0.0"

__all__ = [
    "activities",
    "connect",
    "query",
    "similar_compounds",
    "substructure_search",
    "releases",
    "latest",
    "ReleaseInfo",
    "ReleaseCapabilityError",
    "UnknownReleaseError",
]
