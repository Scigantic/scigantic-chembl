import pytest

import scigantic_chembl as chembl

pytest.importorskip("scigantic_surechembl")


def test_patents_for_aspirin_via_surechembl():
    ids = chembl.surechembl_ids("CHEMBL25")
    assert 1353 in ids
    hits = chembl.patents("chembl25", max_results=5)  # case-insensitive
    assert len(hits) == 5
    assert all(h.url.startswith("https://www.surechembl.org/patent/") for h in hits)
    assert chembl.patents("CHEMBL999999999") == []
