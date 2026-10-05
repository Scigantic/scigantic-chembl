"""Regression: DuckDB inside a Jupyter kernel without ipywidgets.

DuckDB 1.5.5 detects Jupyter and raises InvalidInputException on any change to
enable_progress_bar when ipywidgets is absent, even `SET enable_progress_bar=false`.
The connection setup must survive that. The real condition needs an ipykernel on
an image without ipywidgets (scigantic's minimal/database images); this test
reproduces the raise by wrapping duckdb.connect so that one SET fails the way
DuckDB fails it.
"""

from __future__ import annotations

import duckdb
import pytest

from scigantic_chembl.connection import connect


class _JupyterLikeConnection:
    def __init__(self, real: duckdb.DuckDBPyConnection) -> None:
        self._real = real

    def execute(self, sql: str, *a: object, **k: object) -> duckdb.DuckDBPyConnection:
        if "enable_progress_bar" in sql:
            raise duckdb.InvalidInputException(
                "Invalid Input Error: Could not change the progress bar setting because: "
                "'required package 'ipywidgets' is missing, which is needed to render progress bars in Jupyter'"
            )
        return self._real.execute(sql, *a, **k)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def test_connection_survives_jupyter_progress_bar_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = duckdb.connect
    monkeypatch.setattr(duckdb, "connect", lambda *a, **k: _JupyterLikeConnection(real_connect(*a, **k)))

    con = connect()
    try:
        assert con.execute("SELECT 1").fetchone() == (1,)
    finally:
        con.close()
