# scigantic-chembl

Query ChEMBL directly from a public S3 mirror with DuckDB. No download, no local database to manage.

```python
import scigantic_chembl as chembl

df = chembl.query("""
    SELECT chembl_id, pref_name
    FROM molecule_dictionary
    WHERE pref_name IS NOT NULL
    LIMIT 5
""")
```

That query runs against `s3://scigantic-chembl`, a public mirror of ChEMBL converted to parquet. Nothing is downloaded first.

## Compared to chembl-downloader

[chembl-downloader](https://github.com/cthoyt/chembl-downloader) is the standard way to work with ChEMBL in Python, and it covers every release back to chembl_1, with full offline access once the SQLite dump is downloaded. This package trades that for less setup and two things chembl-downloader doesn't ship on its own: a pre-joined potency table, and similarity search with no separate index build. The trade is release coverage: this mirror carries chembl_35 through chembl_37, and only chembl_37 has the pre-joined and similarity layers. If you need an older release or fully offline access, chembl-downloader is the right tool.

## Potency data, pre-joined

`activities` needs a five-table join and a few correctness filters before it is usable for structure-activity work. That join is already done and stored as `derived/activities_enriched.parquet`:

```python
df = chembl.activities(target_chembl_id="CHEMBL203")  # EGFR: 18,998 rows, 11,202 compounds
```

The filters already applied are the ones that are about correctness rather than taste: `pchembl_value` present, `standard_relation = '='`, no `data_validity_comment`, not a `potential_duplicate`. `confidence_score` and `target_type` are left as columns, not filters, since which rows count as usable SAR data is an analysis choice:

```python
df = chembl.activities(target_chembl_id="CHEMBL203", min_confidence=8)
```

Direct SQL against the raw tables still works with `chembl.query()`.

## Similarity search

```python
gefitinib = "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4"
hits = chembl.similar_compounds(gefitinib, top_k=5)
```

```
    chembl_id  tanimoto
    CHEMBL939  1.000000
  CHEMBL14699  0.919355
CHEMBL4165375  0.916667
 CHEMBL299672  0.857143
CHEMBL4448162  0.857143
```

Every compound with a comparable potency measurement (1.68M of ChEMBL's 2.9M structures) has a precomputed 2048-bit Morgan fingerprint. `similar_compounds` loads them once per process and ranks by Tanimoto similarity with plain numpy. Loading the corpus is the only slow part: about 18 seconds on a typical home connection, faster from inside AWS, and every call after the first in the same process is under half a second. chembl-downloader can do similarity search too, through `chemfp`, but its own docs put building that index at tens of minutes.

This needs rdkit, kept as an optional extra:

```console
$ pip install "scigantic-chembl[similarity]"
```

## What's mirrored

```python
chembl.releases()
```

| release | raw tables | pre-joined activities | similarity search | CYP training set |
|---|---|---|---|---|
| chembl_37 | yes | yes | yes | yes |
| chembl_36 | yes | no | no | yes |
| chembl_35 | yes | no | no | yes |

chembl_36 and chembl_35 are raw-table access only. Their `activities` table is missing a column chembl_37's has (`modality`), so calling `activities()` or `similar_compounds()` on them raises `ReleaseCapabilityError` up front instead of failing partway through a join with a confusing error.

## Installation

```console
$ pip install scigantic-chembl
```

## Command line

```console
$ scigantic-chembl info
$ scigantic-chembl query "SELECT count(*) FROM activities" --release chembl_37
```

## License

MIT-0. See LICENSE.
