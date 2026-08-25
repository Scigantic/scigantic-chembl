import sys
import warnings

import pytest

import scigantic_chembl as chembl
from scigantic_chembl.releases import ReleaseCapabilityError, UnknownReleaseError


def test_releases_lists_known_releases():
    names = {r.release for r in chembl.releases()}
    assert names == {"chembl_37", "chembl_36", "chembl_35"}


def test_latest_is_chembl_37():
    assert chembl.latest() == "chembl_37"


def test_chembl_37_has_full_derived_layer():
    info = {r.release: r for r in chembl.releases()}["chembl_37"]
    assert info.activities_enriched
    assert info.fingerprints
    assert info.pattern_fingerprints
    assert info.cyp_training


def test_chembl_36_is_raw_only():
    info = {r.release: r for r in chembl.releases()}["chembl_36"]
    assert info.raw
    assert not info.activities_enriched
    assert not info.fingerprints
    assert not info.pattern_fingerprints


def test_activities_on_chembl_36_raises_capability_error():
    with pytest.raises(ReleaseCapabilityError):
        chembl.activities(release="chembl_36")


def test_unknown_release_raises():
    with pytest.raises(UnknownReleaseError):
        chembl.query("SELECT 1", release="chembl_99")


def test_falls_back_when_manifest_unreachable():
    releases_module = sys.modules["scigantic_chembl.releases"]
    real_url, real_cache = releases_module._MANIFEST_URL, releases_module._cache
    releases_module._MANIFEST_URL = (
        "https://scigantic-chembl.s3.us-east-1.amazonaws.com/_DOES_NOT_EXIST.json"
    )
    releases_module._cache = None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert chembl.latest() == "chembl_37"
            assert {r.release for r in chembl.releases()} == {
                "chembl_37",
                "chembl_36",
                "chembl_35",
            }
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)
        assert "falling back" in str(caught[0].message)
    finally:
        releases_module._MANIFEST_URL, releases_module._cache = real_url, real_cache
