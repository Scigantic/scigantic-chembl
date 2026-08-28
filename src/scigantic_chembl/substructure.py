"""Substructure search: which compounds actually contain a fragment.

similar_compounds() answers "what's like this molecule." This answers a
different question: "what contains this exact fragment." RDKit's
HasSubstructMatch does the real work, but it parses a molecule and does
graph matching, too slow to run against the whole corpus per query. This
prescreens first with RDKit's PatternFingerprint: a molecule can only
contain the query fragment if every bit the query sets is also set in the
candidate, a cheap, vectorizable containment test that prunes the corpus
down to a small candidate set before the expensive exact check runs.

Requires rdkit: `pip install scigantic-chembl[similarity]`.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import numpy as np

from ._constants import BUCKET, REGION
from .cache import is_cache_enabled as _cache_enabled
from .cache import resolve as _resolve
from .connection import connect
from .releases import _require, _resolve_release

if TYPE_CHECKING:
    import pandas as pd
    from rdkit.Chem import Mol

_FP_BITS = 2048
_FP_BYTES = _FP_BITS // 8
_DEFAULT_MAX_CANDIDATES = 20_000

# One corpus load per (release, process), same pattern as similarity.py.
_corpus_cache: dict[str, tuple[list[str], "np.ndarray"]] = {}


def _pattern_fingerprint_packed(mol: "Mol") -> "np.ndarray":
    from rdkit import Chem, DataStructs

    bits = np.zeros((_FP_BITS,), dtype=np.uint8)
    DataStructs.ConvertToNumpyArray(Chem.PatternFingerprint(mol, fpSize=_FP_BITS), bits)
    return np.packbits(bits)


def _load_corpus(release: str) -> tuple[list[str], "np.ndarray"]:
    if release in _corpus_cache:
        return _corpus_cache[release]

    import pyarrow.parquet as pq

    key = f"{release}/derived/pattern_fingerprints.parquet"
    if _cache_enabled():
        table = pq.read_table(_resolve(key))
    else:
        import pyarrow.fs as pafs

        filesystem = pafs.S3FileSystem(region=REGION, anonymous=True)
        table = pq.read_table(f"{BUCKET}/{key}", filesystem=filesystem)

    ids = table.column("chembl_id").to_pylist()
    raw = table.column("fp").combine_chunks().buffers()[1]
    packed = np.frombuffer(raw, dtype=np.uint8).reshape(len(ids), _FP_BYTES)

    _corpus_cache[release] = (ids, packed)
    return ids, packed


def substructure_search(
    smarts: str,
    release: str | None = None,
    limit: int = 20,
    max_candidates: int = _DEFAULT_MAX_CANDIDATES,
) -> "pd.DataFrame":
    """Find compounds that actually contain a SMARTS substructure.

    Two stages: a fast bit-containment prescreen over every compound's
    precomputed PatternFingerprint, then RDKit's exact HasSubstructMatch
    against only the prescreen survivors, stopping as soon as `limit`
    confirmed matches are found.

    max_candidates bounds how many prescreen survivors the exact stage will
    look at before giving up, so a very generic fragment (matching a large
    fraction of the corpus) can't turn into an unbounded scan. If that cap
    is hit before `limit` matches are found, a warning is raised and the
    result's `.attrs["truncated"]` is True, rather than silently returning
    an incomplete answer that looks the same as a complete one.

    release defaults to the manifest's current latest(). Only that release
    is guaranteed to have a pattern_fingerprints.parquet. Omitting release
    raises a UserWarning naming the release that was resolved; the returned
    frame carries it either way as `.attrs["chembl_release"]`.
    """
    from rdkit import Chem

    release = _resolve_release(release)
    _require(release, "pattern_fingerprints")

    query_mol = Chem.MolFromSmarts(smarts)
    if query_mol is None:
        raise ValueError(f"rdkit could not parse this SMARTS pattern: {smarts!r}")
    query_fp = _pattern_fingerprint_packed(query_mol)

    ids, corpus = _load_corpus(release)
    # Containment: no bit set in the query is absent from the candidate.
    violations = np.bitwise_count(np.bitwise_and(query_fp, np.bitwise_not(corpus))).sum(axis=1)
    candidate_ids = [ids[i] for i in np.nonzero(violations == 0)[0]]

    import pandas as pd

    if not candidate_ids:
        result = pd.DataFrame(columns=["chembl_id", "canonical_smiles"])
        result.attrs["truncated"] = False
        result.attrs["candidates_examined"] = 0
        result.attrs["chembl_release"] = release
        return result

    pool_truncated = len(candidate_ids) > max_candidates
    examined_ids = candidate_ids[:max_candidates]

    con = connect(release)
    try:
        path = _resolve(f"{release}/derived/activities_enriched.parquet")
        placeholders = ",".join("?" for _ in examined_ids)
        rows = con.execute(
            f"""SELECT DISTINCT compound_chembl_id, canonical_smiles
                FROM read_parquet('{path}')
                WHERE compound_chembl_id IN ({placeholders})""",
            examined_ids,
        ).fetchall()
    finally:
        con.close()

    matches = []
    for chembl_id, smiles in rows:
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None and mol.HasSubstructMatch(query_mol):
            matches.append((chembl_id, smiles))
            if len(matches) >= limit:
                break

    truncated = pool_truncated and len(matches) < limit
    if truncated:
        warnings.warn(
            f"examined the {max_candidates:,}-candidate cap without finding {limit} matches "
            f"({len(candidate_ids):,} candidates passed the prescreen); raise max_candidates "
            "to look further, or narrow the SMARTS",
            stacklevel=2,
        )

    result = pd.DataFrame(matches, columns=["chembl_id", "canonical_smiles"])
    result.attrs["truncated"] = truncated
    result.attrs["candidates_examined"] = len(rows)
    result.attrs["chembl_release"] = release
    return result
