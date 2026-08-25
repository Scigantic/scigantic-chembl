"""DuckDB connection helpers. No download: queries run against the public
S3 mirror over httpfs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._constants import BUCKET, DEFAULT_RELEASE, REGION
from .releases import _validate_release

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

# Registered as views on connect() so plain SQL can reference a table by
# name instead of a full read_parquet() path. Every table under
# <release>/parquet/ is still reachable that way even if it's not listed
# here -- this is just the set worth naming up front.
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


def connect(release: str = DEFAULT_RELEASE) -> "duckdb.DuckDBPyConnection":
    """Open a DuckDB connection against s3://scigantic-chembl.

    `SELECT * FROM activities` works directly; any other table under
    `<release>/parquet/` is reachable with
    `read_parquet('s3://scigantic-chembl/<release>/parquet/<table>.parquet')`.
    """
    import duckdb

    _validate_release(release)

    con = duckdb.connect()
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


def query(sql: str, release: str = DEFAULT_RELEASE) -> "pd.DataFrame":
    """Run SQL against a release and return a pandas DataFrame.

    Opens a new connection per call. For several queries against the same
    release, call connect() once and reuse it instead.
    """
    con = connect(release)
    try:
        return con.execute(sql).df()
    finally:
        con.close()
