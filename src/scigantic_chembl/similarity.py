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

from ._constants import BUCKET
from .releases import _require, latest

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

    import pyarrow.fs as pafs
    import pyarrow.parquet as pq

    # pyarrow's own S3 filesystem, not DuckDB: reading the packed-byte
    # column straight off its Arrow buffer is what keeps this fast. Going
    # through DuckDB's dataframe conversion instead turns 1.68M individual
    # 256-byte python bytes objects and a few seconds becomes minutes.
    filesystem = pafs.S3FileSystem(region="us-east-1", anonymous=True)
    key = f"{BUCKET}/{release}/derived/fingerprints.parquet"
    table = pq.read_table(key, filesystem=filesystem)

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
    calls in the same process reuse it.
    """
    release = release or latest()
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

    return pd.DataFrame(
        {
            "chembl_id": [ids[i] for i in order],
            "tanimoto": tanimoto[order],
        }
    )
