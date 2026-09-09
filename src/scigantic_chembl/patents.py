"""The pointer from a ChEMBL compound into patent chemistry.

SureChEMBL (EMBL-EBI) holds 31M compounds extracted from 45M patents and
is keyed by its own ids. scigantic-surechembl maps a ChEMBL id to those
ids through UniChem and takes the union of their patent lists; these two
functions call it, so a scigantic-chembl user can get from a compound to
its patents without knowing that package exists. Everything else about a
patent (its text, the chemistry extracted from it, Solr and structure
search, the ChEMBL/BindingDB joins in the other direction) lives there.

Needs the `patents` extra: `pip install "scigantic-chembl[patents]"`.
"""

from __future__ import annotations

from typing import Any


def _surechembl() -> Any:
    try:
        import scigantic_surechembl
    except ImportError as exc:
        raise ImportError(
            "this needs scigantic-surechembl. Install with: pip install 'scigantic-chembl[patents]'"
        ) from exc
    return scigantic_surechembl


def surechembl_ids(chembl_id: str) -> list[int]:
    """SureChEMBL compound ids for a ChEMBL id, via UniChem. More than one
    is common: a structure can sit under several SureChEMBL ids (aspirin,
    CHEMBL25, is 1353 and 29350479). [] if UniChem has no mapping."""
    return list(_surechembl().surechembl_ids_for("chembl", chembl_id.strip().upper()))


def patents(chembl_id: str, max_results: int = 100) -> list[Any]:
    """Patents in which a ChEMBL compound was found, as
    scigantic_surechembl.PatentHit records (doc_id, title,
    publication_date, assignee, url), the union over every SureChEMBL id
    the ChEMBL id maps to. Aspirin is in ~700,000 documents, so for a
    common compound this is a sample; `scigantic_surechembl.
    count_patents_for_compound()` gives the total per id."""
    return list(_surechembl().patents_for_chembl(chembl_id.strip().upper(), max_results=max_results))
