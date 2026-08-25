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

[chembl-downloader](https://github.com/cthoyt/chembl-downloader) is the standard way to work with ChEMBL in Python. It covers every release back to chembl_1, and once the SQLite dump is downloaded it works fully offline. It can also do similarity and substructure search, through `chemfp` and an RDKit `SubstructLibrary` it builds locally. This package trades that release range for less setup: a pre-joined potency table, and similarity and substructure search over fingerprints the mirror already precomputes, so there's no local index to build before a query runs. `enable_cache()` closes some of the offline gap, see below, but the mirror here only carries chembl_35 through chembl_37, and an older release is still a job for chembl-downloader.

## Potency data, pre-joined

`activities` needs a five-table join and a few correctness filters before it's usable for structure-activity work. That join is already done, stored as `derived/activities_enriched.parquet`:

```python
df = chembl.activities(target_chembl_id="CHEMBL203")  # EGFR: 18,998 rows, 11,202 compounds
```

The filters already applied are about correctness, not taste: `pchembl_value` present, `standard_relation = '='`, no `data_validity_comment`, not a `potential_duplicate`. `confidence_score` and `target_type` stay as columns rather than filters, since which rows count as usable SAR data is an analysis choice:

```python
df = chembl.activities(min_confidence=8, limit=50_000)
```

`min_confidence` won't do anything combined with a single `target_chembl_id`: ChEMBL curates `confidence_score` per target entry, not per measurement, so every row for one target shares the same confidence class (verified against the live corpus: zero targets have a mixed score). It narrows results when querying across targets, like the example above.

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

## Substructure search

Similarity search answers "what's like this molecule." This answers a different question: "what actually contains this fragment."

```python
from rdkit import Chem

gefitinib = "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4"
gefitinib_scaffold = Chem.MolToSmarts(Chem.MolFromSmiles(gefitinib))
hits = chembl.substructure_search(gefitinib_scaffold, limit=50)
```

```
    chembl_id                                                        canonical_smiles
CHEMBL4165375   Fc1ccc(Nc2ncnc3cc(OCCCN4CCOCC4)c(OCCCN4CCOCC4)cc23)cc1Cl
CHEMBL1788321   COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OC[C@H](O)CN1CCOCC1
    CHEMBL939   COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1
```

(9 matches total, truncated for space here; CHEMBL939 is gefitinib itself, the rest are close analogues and prodrugs.)

RDKit's exact `HasSubstructMatch` is too slow to run against 1.68M compounds per query, so this prescreens first with a precomputed `PatternFingerprint`: a molecule can only contain the query fragment if every bit the query sets is also set in the candidate, a cheap containment test over packed bytes. Only prescreen survivors get the expensive exact check, stopping as soon as `limit` confirmed matches are found.

**How narrow the prescreen is depends on how specific the query fragment is, not on this package.** A small, generic ring system (a bare quinazoline, say) is a weak filter, over a million of the 1.68M compounds pass it, because PatternFingerprint discriminates on structural complexity, and small fragments have little of it. A large, specific fragment like the full example above prescreens to 34 candidates before the exact stage even starts. `max_candidates` (default 20,000) bounds how many prescreen survivors get exact-matched, so an overly generic query can't turn into an unbounded scan; hitting that cap before finding `limit` matches raises a warning and sets `result.attrs["truncated"] = True`, rather than silently returning a partial answer that looks complete.

## Working offline

Off by default, since zero setup is the whole point. Turn it on when you want to run the same queries repeatedly without re-fetching from S3, or work with no network at all after the first pull:

```python
import scigantic_chembl as chembl

chembl.enable_cache()
df = chembl.activities(target_chembl_id="CHEMBL203")  # downloads once, then reads from disk
```

`activities()`, `similar_compounds()` and `substructure_search()` each need exactly one derived file, so caching downloads that one file to `~/.cache/scigantic-chembl` (override with `enable_cache(cache_dir=...)` or the `SCIGANTIC_CHEMBL_CACHE` environment variable) and reuses it after that.

`connect()` and `query()` don't participate in this. `connect()` registers ten core tables as views on every call, several over 1 GB, so caching them there would mean any call eagerly downloads everything regardless of what the query actually touches. Cache one table yourself if you want it locally: `chembl.cache_resolve("chembl_37/parquet/molecule_dictionary.parquet")` downloads it and returns the local path, usable directly in `read_parquet(...)`.

## What's mirrored

```python
chembl.releases()
```

| release | raw tables | pre-joined activities | similarity search | substructure search | CYP training set |
|---|---|---|---|---|---|
| chembl_37 | yes | yes | yes | yes | yes |
| chembl_36 | yes | no | no | no | yes |
| chembl_35 | yes | no | no | no | yes |

chembl_36 and chembl_35 are raw-table access only: their `activities` table is missing a column chembl_37's has (`modality`), so calling `activities()`, `similar_compounds()`, or `substructure_search()` on either one raises `ReleaseCapabilityError` up front instead of failing partway through a join with a confusing error.

This table isn't hardcoded. `releases()` reads a small manifest that the mirror's own weekly cron regenerates by probing the bucket directly, so a new ChEMBL release shows up here without waiting on a new version of this package. If the manifest can't be reached, calls fall back to the snapshot shipped with whatever version you have installed and print a warning, rather than failing outright.

## Command line

```console
$ scigantic-chembl info
$ scigantic-chembl query "SELECT count(*) FROM activities" --release chembl_37
```

## License

MIT-0. See [LICENSE](LICENSE).
