"""DuckDB connection helpers. Queries run against the public S3 mirror over
httpfs, no download.

This module deliberately does not participate in enable_cache() (see
cache.py): connect() registers all ten core tables as views on every call,
several over 1 GB, so caching them here would mean any call to connect()
or query() eagerly downloads everything regardless of what the query
actually touches. Caching applies to activities()/similar_compounds()/
substructure_search() instead, each of which needs exactly one known file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._constants import BUCKET, REGION
from .releases import _resolve_release, _validate_release

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

# Registered as views on connect() so plain SQL can reference a table by
# name instead of a full read_parquet() path. Every table under
# <release>/parquet/ is still reachable that way even if it's not listed
# here; this is just the set worth naming up front.
_CORE_TABLES = (
    "activities",
    "assays",
    "target_dictionary",
    "molecule_dictionary",
    "compound_structures",
    "compound_properties",
    "molecule_synonyms",
    "docs",
    "drug_mechanism",
    "drug_indication",
)


def connect(release: str | None = None) -> "duckdb.DuckDBPyConnection":
    """Open a DuckDB connection against s3://scigantic-chembl.

    `SELECT * FROM activities` works directly; any other table under
    `<release>/parquet/` is reachable with
    `read_parquet('s3://scigantic-chembl/<release>/parquet/<table>.parquet')`.

    release defaults to whatever the live manifest currently calls latest(),
    resolved at call time rather than import time; omitting it raises a
    UserWarning naming the release that was resolved, since that resolution
    isn't stable across processes and this connection carries no attribute
    of its own to recover it from afterward.
    """
    import duckdb

    release = _resolve_release(release)
    _validate_release(release)

    con = duckdb.connect()
    # DuckDB auto-shows an ASCII progress bar for queries it estimates will
    # take a while, on stdout, regardless of whether that's a real
    # terminal. Fine for the ops scripts in the main scigantic repo that
    # already set this; surprising output for a library call in a notebook
    # or script, so it's off here by default.
    con.execute("SET enable_progress_bar=false")
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"SET s3_region='{REGION}'")
    # The mirror is public-read. Without this, DuckDB looks for AWS
    # credentials and fails on a machine that has none configured.
    con.execute(
        "CREATE OR REPLACE SECRET scigantic_chembl "
        "(TYPE s3, PROVIDER config, KEY_ID '', SECRET '')"
    )

    base = f"s3://{BUCKET}/{release}/parquet"
    for table in _CORE_TABLES:
        con.execute(
            f"CREATE OR REPLACE VIEW {table} AS "
            f"SELECT * FROM read_parquet('{base}/{table}.parquet')"
        )
    return con


def query(sql: str, release: str | None = None) -> "pd.DataFrame":
    """Run SQL against a release and return a pandas DataFrame.

    Opens a new connection per call. For several queries against the same
    release, call connect() once and reuse it instead.
    """
    release = _resolve_release(release)
    con = connect(release)
    try:
        df = con.execute(sql).df()
        df.attrs["chembl_release"] = release
        return df
    finally:
        con.close()
