import scigantic_chembl as chembl


def test_egfr_activities():
    # CHEMBL203 is EGFR. Exact count verified against the live mirror; update
    # this if chembl_37 is ever replaced by a different release under the
    # same "current" pointer.
    df = chembl.activities(target_chembl_id="CHEMBL203")
    assert len(df) == 18998
    assert df["compound_chembl_id"].nunique() == 11202
    assert (df["target_chembl_id"] == "CHEMBL203").all()


def test_activities_sorted_by_potency_descending():
    df = chembl.activities(target_chembl_id="CHEMBL203", limit=100)
    assert df["pchembl_value"].is_monotonic_decreasing


def test_min_confidence_filter_narrows_results():
    unfiltered = chembl.activities(target_chembl_id="CHEMBL203")
    filtered = chembl.activities(target_chembl_id="CHEMBL203", min_confidence=8)
    assert len(filtered) <= len(unfiltered)
    assert (filtered["confidence_score"] >= 8).all()
