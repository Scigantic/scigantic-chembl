"""Query ChEMBL directly from a public S3 mirror. No download, no local database."""

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

__version__ = "0.1.0"

__all__ = [
    "activities",
    "connect",
    "query",
    "similar_compounds",
    "releases",
    "latest",
    "ReleaseInfo",
    "ReleaseCapabilityError",
    "UnknownReleaseError",
]
