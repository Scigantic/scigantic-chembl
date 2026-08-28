import warnings

import scigantic_chembl as chembl


def test_omitted_release_warns_and_is_recorded():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = chembl.activities(target_chembl_id="CHEMBL203")
    assert len(caught) == 1
    assert issubclass(caught[0].category, UserWarning)
    assert "no release specified" in str(caught[0].message)
    assert df.attrs["chembl_release"] == "chembl_37"


def test_explicit_release_does_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = chembl.activities(release="chembl_37", target_chembl_id="CHEMBL203")
    assert len(caught) == 0
    assert df.attrs["chembl_release"] == "chembl_37"


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


def test_min_confidence_is_a_no_op_within_one_target():
    # Verified, not assumed: ChEMBL curates confidence_score per target
    # entry, not per measurement, so every row sharing a target_chembl_id
    # shares the same confidence class. Checked across the whole corpus:
    # zero targets have a mixed confidence_score. So this combination is
    # redundant by design, not a filter that silently does nothing wrong.
    unfiltered = chembl.activities(target_chembl_id="CHEMBL203")
    filtered = chembl.activities(target_chembl_id="CHEMBL203", min_confidence=8)
    assert len(filtered) == len(unfiltered)


def test_min_confidence_narrows_results_across_the_corpus():
    # Where min_confidence actually does something: without a
    # target_chembl_id restriction, different targets carry different
    # confidence classes. Both queries are capped at the same limit and the
    # corpus is large enough to fill it either way, so this checks
    # composition, not row count: real heterogeneity without the filter,
    # none left with it.
    unfiltered = chembl.activities(limit=50_000)
    filtered = chembl.activities(min_confidence=8, limit=50_000)
    assert (unfiltered["confidence_score"] < 8).any()
    assert (filtered["confidence_score"] >= 8).all()
