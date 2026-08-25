"""Shared constants: where the mirror lives, and what it currently carries."""

BUCKET = "scigantic-chembl"
REGION = "us-east-1"
DEFAULT_RELEASE = "chembl_37"

# What's actually mirrored today, and which derived artifacts each release
# carries. Bump this when the mirror gains a release or an artifact -- see
# infrastructure/kubernetes/chembl-release-check-cronjob.yaml in the main
# scigantic repo, which is what keeps the mirror itself current. chembl_36
# and chembl_35 are raw-table access only: their `activities` table is
# missing a column (`modality`) that chembl_37's has, so the pre-joined
# build fails on them rather than silently producing a subtly wrong join.
RELEASES = {
    "chembl_37": {
        "raw": True,
        "activities_enriched": True,
        "fingerprints": True,
        "cyp_training": True,
    },
    "chembl_36": {
        "raw": True,
        "activities_enriched": False,
        "fingerprints": False,
        "cyp_training": True,
    },
    "chembl_35": {
        "raw": True,
        "activities_enriched": False,
        "fingerprints": False,
        "cyp_training": True,
    },
}
