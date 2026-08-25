<h1 align="center">scigantic-chembl</h1>

<p align="center">
    <a href="https://github.com/Scigantic/scigantic-chembl/actions/workflows/ci.yml">
        <img alt="CI" src="https://github.com/Scigantic/scigantic-chembl/actions/workflows/ci.yml/badge.svg" /></a>
    <a href="https://pypi.org/project/scigantic-chembl/">
        <img alt="PyPI" src="https://img.shields.io/pypi/v/scigantic-chembl" /></a>
    <a href="https://pypi.org/project/scigantic-chembl/">
        <img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/scigantic-chembl" /></a>
    <a href="https://github.com/Scigantic/scigantic-chembl/blob/main/LICENSE">
        <img alt="License" src="https://img.shields.io/github/license/Scigantic/scigantic-chembl" /></a>
</p>

Query ChEMBL directly from a public S3 mirror with DuckDB.

```python
import scigantic_chembl as chembl

df = chembl.query("""
    SELECT chembl_id, pref_name
    FROM molecule_dictionary
    WHERE pref_name IS NOT NULL
    LIMIT 5
""")
```

That query runs against `s3://scigantic-chembl` over DuckDB's httpfs extension. Nothing is downloaded first, and there's no local database file sitting on disk afterward.

## Installation

```console
$ pip install scigantic-chembl
```

## Compared to chembl-downloader

[chembl-downloader](https://github.com/cthoyt/chembl-downloader) is the standard way to work with ChEMBL in Python. It covers every release back to chembl_1, and once the SQLite dump is downloaded it works fully offline. This package gives up that range for less setup and two things chembl-downloader doesn't ship on its own: a pre-joined potency table, and similarity search with no separate index build. The mirror here only carries chembl_35 through chembl_37, and only chembl_37 has the pre-joined and similarity layers, so an older release or fully offline work is still a job for chembl-downloader.

## Potency data, pre-joined

`activities` needs a five-table join and a few correctness filters before it's usable for structure-activity work. That join is already done, stored as `derived/activities_enriched.parquet`:

```python
df = chembl.activities(target_chembl_id="CHEMBL203")  # EGFR: 18,998 rows, 11,202 compounds
```

The filters already applied are about correctness, not taste: `pchembl_value` present, `standard_relation = '='`, no `data_validity_comment`, not a `potential_duplicate`. `confidence_score` and `target_type` stay as columns rather than filters, since which rows count as usable SAR data is an analysis choice:

```python
df = chembl.activities(target_chembl_id="CHEMBL203", min_confidence=8)
```

`chembl.query()` still reaches the raw tables directly for anything the join leaves out.

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

CHEMBL939 is gefitinib itself. Every compound with a comparable potency measurement (1.68M of ChEMBL's 2.9M structures) has a precomputed 2048-bit Morgan fingerprint, kept packed in memory and compared with numpy's `bitwise_count` rather than unpacked bit by bit. The corpus loads once per process, about 18 seconds on a typical home connection and faster from inside AWS; every call after that in the same process is under half a second. chembl-downloader can do similarity search too, through `chemfp`, but its own docs put building that index at tens of minutes.

Similarity search needs rdkit to encode the query molecule, so it's kept as an optional extra:

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

chembl_36 and chembl_35 are raw-table access only: their `activities` table is missing a column chembl_37's has (`modality`), so calling `activities()` or `similar_compounds()` on either one raises `ReleaseCapabilityError` up front instead of failing partway through a join with a confusing error.

## Command line

```console
$ scigantic-chembl info
$ scigantic-chembl query "SELECT count(*) FROM activities" --release chembl_37
```

## License

MIT-0. See [LICENSE](LICENSE).
