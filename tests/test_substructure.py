import warnings

import pytest

import scigantic_chembl as chembl

rdkit = pytest.importorskip("rdkit")
from rdkit import Chem  # noqa: E402

# Gefitinib's full scaffold as a SMARTS query. Verified against the live
# mirror: 9 real matches (close analogues and gefitinib itself, CHEMBL939),
# not truncated. A small query like a bare quinazoline ring is a much
# weaker prescreen filter (a million-plus candidates for this corpus) since
# PatternFingerprint discriminates on structural complexity; this scaffold
# is large enough to prescreen down to 34 candidates before the exact
# match step even runs.
GEFITINIB_SMILES = "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4"
GEFITINIB_SCAFFOLD = Chem.MolToSmarts(Chem.MolFromSmiles(GEFITINIB_SMILES))

# A large, specific fragment with zero real matches in the corpus (verified:
# 681 prescreen candidates, all correctly rejected by the exact stage).
# The dibromo substitution doesn't co-occur with the rest of this scaffold
# in any real ChEMBL compound.
IMPOSSIBLE_FRAGMENT = (
    "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(Br)=C(Br)C=C3)OCCCN4CCOCC4"
)


def test_substructure_search_finds_known_matches():
    hits = chembl.substructure_search(GEFITINIB_SCAFFOLD, limit=50, max_candidates=1000)
    assert list(hits.columns) == ["chembl_id", "canonical_smiles"]
    assert len(hits) == 9
    assert "CHEMBL939" in set(hits["chembl_id"])
    assert hits.attrs["truncated"] is False


def test_every_returned_hit_actually_contains_the_fragment():
    # The correctness property that matters: no false positives make it
    # past the exact-match stage, regardless of how loose the prescreen is.
    query_mol = Chem.MolFromSmarts(GEFITINIB_SCAFFOLD)
    hits = chembl.substructure_search(GEFITINIB_SCAFFOLD, limit=50, max_candidates=1000)
    for smiles in hits["canonical_smiles"]:
        mol = Chem.MolFromSmiles(smiles)
        assert mol.HasSubstructMatch(query_mol)


def test_substructure_search_respects_limit():
    hits = chembl.substructure_search(GEFITINIB_SCAFFOLD, limit=3, max_candidates=1000)
    assert len(hits) <= 3


def test_substructure_search_on_release_without_pattern_fingerprints_raises():
    from scigantic_chembl.releases import ReleaseCapabilityError

    with pytest.raises(ReleaseCapabilityError):
        chembl.substructure_search(GEFITINIB_SCAFFOLD, release="chembl_36")


def test_invalid_smarts_raises_value_error():
    with pytest.raises(ValueError):
        chembl.substructure_search("not a smarts pattern (((", limit=1)


def test_confirmed_absent_fragment_returns_empty_not_truncated():
    hits = chembl.substructure_search(IMPOSSIBLE_FRAGMENT, limit=10, max_candidates=1000)
    assert len(hits) == 0
    assert hits.attrs["candidates_examined"] == 681
    assert hits.attrs["truncated"] is False


def test_truncation_warns_and_flags_when_cap_too_low():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hits = chembl.substructure_search(
            GEFITINIB_SCAFFOLD, limit=50, max_candidates=1
        )
    assert hits.attrs["truncated"] is True
    assert len(caught) == 1
    assert "cap" in str(caught[0].message)
