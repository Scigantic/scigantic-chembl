"""The pre-joined, pre-filtered potency table.

activities is a five-table join (activities, assays, target_dictionary,
molecule_dictionary, compound_structures, docs) with four correctness
filters most callers apply anyway: pchembl_value present, standard_relation
'=', no data_validity_comment, not a potential_duplicate. This is that join
done once and stored as derived/activities_enriched.parquet, not
recomputed on every call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cache import resolve as _resolve
from .connection import connect
from .releases import _require, _resolve_release

if TYPE_CHECKING:
    import pandas as pd


def activities(
    release: str | None = None,
    target_chembl_id: str | None = None,
    min_confidence: int | None = None,
    limit: int | None = None,
) -> "pd.DataFrame":
    """Potency measurements, already joined and filtered.

    confidence_score and target_type ride along as columns rather than
    filters -- which rows count as usable SAR data is an analysis choice,
    not something to bake in silently. Pass min_confidence to apply the
    common confidence_score >= 8 convention yourself.

    release defaults to the manifest's current latest(). Only that release
    is guaranteed to carry this file; call releases() to check which ones
    do, and expect ReleaseCapabilityError on the ones that don't. Omitting
    it raises a UserWarning naming the release that was resolved; the
    returned frame carries it either way as `.attrs["chembl_release"]`.
    """
    release = _resolve_release(release)
    _require(release, "activities_enriched")
    con = connect(release)
    try:
        path = _resolve(f"{release}/derived/activities_enriched.parquet")
        con.execute(
            "CREATE OR REPLACE VIEW activities_enriched AS "
            f"SELECT * FROM read_parquet('{path}')"
        )
        where: list[str] = []
        params: list[str | int] = []
        if target_chembl_id is not None:
            where.append("target_chembl_id = ?")
            params.append(target_chembl_id)
        if min_confidence is not None:
            where.append("confidence_score >= ?")
            params.append(min_confidence)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        sql = f"SELECT * FROM activities_enriched {clause} ORDER BY pchembl_value DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        df = con.execute(sql, params).df()
        df.attrs["chembl_release"] = release
        return df
    finally:
        con.close()
