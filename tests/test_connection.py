"""Real queries against the live public mirror, no mocks.

Network-dependent by design: the whole point of this package is that it
answers real queries against real data with no local setup, so that is what
gets tested.
"""

import warnings

import scigantic_chembl as chembl


def test_query_returns_dataframe_with_expected_columns():
    df = chembl.query(
        "SELECT chembl_id, pref_name FROM molecule_dictionary "
        "WHERE pref_name IS NOT NULL LIMIT 5"
    )
    assert list(df.columns) == ["chembl_id", "pref_name"]
    assert len(df) == 5


def test_query_against_chembl_36_raw_table():
    df = chembl.query("SELECT count(*) AS n FROM target_dictionary", release="chembl_36")
    assert df["n"].iloc[0] > 0


def test_connect_reuse_across_two_queries():
    con = chembl.connect()
    try:
        a = con.execute("SELECT count(*) FROM activities").fetchone()[0]
        b = con.execute("SELECT count(*) FROM assays").fetchone()[0]
        assert a > 0
        assert b > 0
    finally:
        con.close()


def test_query_omitted_release_warns_and_is_recorded():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = chembl.query("SELECT 1")
    assert len(caught) == 1
    assert issubclass(caught[0].category, UserWarning)
    assert "no release specified" in str(caught[0].message)
    assert df.attrs["chembl_release"] == "chembl_37"


def test_query_explicit_release_does_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = chembl.query("SELECT 1", release="chembl_37")
    assert len(caught) == 0
    assert df.attrs["chembl_release"] == "chembl_37"


def test_connect_omitted_release_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        con = chembl.connect()
    try:
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)
        assert "no release specified" in str(caught[0].message)
        assert "chembl_37" in str(caught[0].message)
    finally:
        con.close()


def test_connect_explicit_release_does_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        con = chembl.connect(release="chembl_37")
    try:
        assert len(caught) == 0
    finally:
        con.close()
