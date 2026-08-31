# Changelog

All notable changes to this project are documented here. Versions correspond to PyPI releases.

## 0.4.5 - 2026-08-31

- Fixed a concurrency race in the local cache (`enable_cache()`): concurrent callers resolving the same key could each trigger a duplicate download, and two callers finishing a download at the same time could collide on a shared temp filename and raise `FileNotFoundError` on `os.replace()`. Fixed with a per-key lock and a unique temp filename per download attempt. Ported from the same fix already shipped in scigantic-bindingdb, which forked from this package before that fix existed here.
- Added a "Data license" section to the README: ChEMBL's underlying data is CC BY-SA 3.0, separate from and not superseded by this package's own MIT-0 code license.
- Added upper bounds to the `duckdb`, `pyarrow`, `numpy`, and `pandas` dependency constraints so a future breaking major release doesn't silently pull in an untested version.
- Added this CHANGELOG.md.

## 0.4.4 - 2026-08-28

Published as a catch-up release. 0.4.2, 0.4.3, and this ETag-caching fix had all been merged to `main` with their versions bumped in `pyproject.toml`, but no tag had been pushed for any of them, so `publish.yml` never ran and PyPI stayed on 0.4.1 for three releases. This release tags and publishes all three changes at once; no code changed beyond what had already merged.

- Cache the S3 ETag alongside the corpus instead of re-fetching it on every call (#4).

### 0.4.3 (not independently published; shipped together with 0.4.4 above)

- Record the source object's S3 ETag alongside `chembl_release` (#2).

### 0.4.2 (not independently published; shipped together with 0.4.4 above)

- Warn and record which release an omitted-release call actually used (#1).

## 0.4.1 - 2026-08-25

- Added the interrupted-download test 0.4.0 claimed to have but didn't.

## 0.4.0 - 2026-08-25

- Added optional local caching (`enable_cache()` / `disable_cache()`).

## 0.3.1 - 2026-08-25

- Fixed a misleading README example and unexpected progress-bar output.

## 0.3.0 - 2026-08-25

- Added substructure search.
- Fixed a real `__version__` drift bug.

## 0.2.1 - 2026-08-25

- Fixed real mypy findings.
- Added `python -m scigantic_chembl` support.

## 0.2.0 - 2026-08-24

- Reads the live release manifest instead of a hardcoded table.

## 0.1.1 - 2026-08-24

- Fixed PyPI summary wording, added repo links and `py.typed`.

## 0.1.0 - 2026-08-24

- Initial release: query ChEMBL from S3 with DuckDB, no download step.
