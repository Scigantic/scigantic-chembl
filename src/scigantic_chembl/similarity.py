"""Structure similarity search over precomputed fingerprints.

Every compound carrying a comparable potency measurement (1.68M of ChEMBL's
2.9M structures) has a precomputed 2048-bit Morgan fingerprint (radius 2),
packed to 256 bytes. Fingerprints are kept packed in memory and compared
with numpy's bitwise_count, so a search never unpacks to a 2048-column
array -- that difference is what keeps this to a fraction of a second
against a corpus that would otherwise be several gigabytes unpacked.

Requires rdkit to encode the query molecule: `pip install
scigantic-chembl[similarity]`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ._constants import BUCKET, REGION
from .cache import _etag
from .cache import is_cache_enabled as _cache_enabled
from .cache import resolve as _resolve
from .releases import _require, _resolve_release

if TYPE_CHECKING:
    import pandas as pd

_FP_BITS = 2048
_FP_BYTES = _FP_BITS // 8

# One corpus load per (release, process): reused across calls in the same
# session rather than re-fetched from S3 every time.
_corpus_cache: dict[str, tuple[list[str], "np.ndarray"]] = {}


def _fingerprint_packed(smiles: str) -> "np.ndarray":
    """Encode a query SMILES the same way the stored corpus was encoded."""
    try:
        from rdkit import Chem
        from rdkit.Chem import rdFingerprintGenerator
    except ImportError as exc:
        raise ImportError(
            "similar_compounds() needs rdkit. Install with: "
            "pip install 'scigantic-chembl[similarity]'"
        ) from exc

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"rdkit could not parse this SMILES: {smiles!r}")
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=_FP_BITS)
    bits = generator.GetFingerprintAsNumPy(mol).astype(np.uint8)
    return np.packbits(bits)


def _load_corpus(release: str) -> tuple[list[str], "np.ndarray"]:
    if release in _corpus_cache:
        return _corpus_cache[release]

    import pyarrow.parquet as pq

    key = f"{release}/derived/fingerprints.parquet"
    if _cache_enabled():
        # A local path from here needs no filesystem argument.
        table = pq.read_table(_resolve(key))
    else:
        import pyarrow.fs as pafs

        # pyarrow's own S3 filesystem, not DuckDB: reading the packed-byte
        # column straight off its Arrow buffer is what keeps this fast. Going
        # through DuckDB's dataframe conversion instead turns 1.68M individual
        # 256-byte python bytes objects and a few seconds becomes minutes.
        filesystem = pafs.S3FileSystem(region=REGION, anonymous=True)
        table = pq.read_table(f"{BUCKET}/{key}", filesystem=filesystem)

    ids = table.column("chembl_id").to_pylist()
    raw = table.column("fp").combine_chunks().buffers()[1]
    packed = np.frombuffer(raw, dtype=np.uint8).reshape(len(ids), _FP_BYTES)

    _corpus_cache[release] = (ids, packed)
    return ids, packed


def similar_compounds(
    smiles: str,
    release: str | None = None,
    top_k: int = 20,
) -> "pd.DataFrame":
    """Rank the corpus by Tanimoto similarity to a query SMILES.

    release defaults to the manifest's current latest(). Only that release
    is guaranteed to have a fingerprints.parquet. The first call in a
    process pays for loading the corpus from S3 (a few seconds); later
    calls in the same process reuse it. Omitting release raises a
    UserWarning naming the release that was resolved; the returned frame
    carries it either way as `.attrs["chembl_release"]`, plus the source
    parquet file's current S3 ETag as `.attrs["chembl_etag"]` (None if
    that HEAD request fails).
    """
    release = _resolve_release(release)
    _require(release, "fingerprints")
    query_fp = _fingerprint_packed(smiles)
    ids, corpus = _load_corpus(release)

    intersection = np.bitwise_count(corpus & query_fp).sum(axis=1, dtype=np.int32)
    union = np.bitwise_count(corpus | query_fp).sum(axis=1, dtype=np.int32)
    tanimoto = np.divide(
        intersection,
        union,
        out=np.zeros(len(ids), dtype=np.float64),
        where=union != 0,
    )

    order = np.argsort(-tanimoto, kind="stable")[:top_k]
    import pandas as pd

    result = pd.DataFrame(
        {
            "chembl_id": [ids[i] for i in order],
            "tanimoto": tanimoto[order],
        }
    )
    result.attrs["chembl_release"] = release
    result.attrs["chembl_etag"] = _etag(f"{release}/derived/fingerprints.parquet")
    return result
