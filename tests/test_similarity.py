import pytest

import scigantic_chembl as chembl

rdkit = pytest.importorskip("rdkit")

# PubChem CID 123631, canonical SMILES for gefitinib.
GEFITINIB_SMILES = "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4"


def test_similar_compounds_returns_query_itself_as_top_hit():
    hits = chembl.similar_compounds(GEFITINIB_SMILES, top_k=5)
    assert list(hits.columns) == ["chembl_id", "tanimoto"]
    assert len(hits) == 5
    assert hits["tanimoto"].iloc[0] == pytest.approx(1.0)
    assert hits["tanimoto"].is_monotonic_decreasing


def test_similar_compounds_on_release_without_fingerprints_raises():
    from scigantic_chembl.releases import ReleaseCapabilityError

    with pytest.raises(ReleaseCapabilityError):
        chembl.similar_compounds(GEFITINIB_SMILES, release="chembl_36")


def test_invalid_smiles_raises_value_error():
    with pytest.raises(ValueError):
        chembl.similar_compounds("not a smiles string")
