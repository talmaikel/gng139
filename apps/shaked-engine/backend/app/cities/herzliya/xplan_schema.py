"""
Herzliya XPlan (Israeli national iplan.gov.il ArcGIS) designation schema.

Mirrors the mavat_code / category vocabulary already established by the
Herzliya data-pipeline POC (see `POC/app/xplan.py` in this monorepo, kept
out of this app's dependency graph per the isolation rule — the constants
below are duplicated deliberately so `apps/shaked-engine` never imports
from `POC`).
"""

# mavat_code values that represent a pure residential land-use designation.
PURE_RESIDENTIAL_CODES: set[int] = {10, 20, 60, 100, 140}

# mavat_code values whose designation is ambiguous on XPlan alone and requires
# a secondary source (e.g. the municipal archive's permit-page designation).
AMBIGUOUS_CODES: set[int] = {995, 999}

# Candidate categories, ordered by screening priority (first match wins).
CATEGORY_PRIORITY: list[str] = [
    "preservation",
    "existing_renewal_plan",
    "metro",
    "urban_renewal_compound",
    "filtered_landuse",
    "needs_verification",
    "primary_candidate",
]

# Categories that are eligible to enter the dossier-generation queue.
QUEUE_ELIGIBLE_CATEGORIES: set[str] = {"primary_candidate", "needs_verification"}


def is_eligible_residential_code(mavat_code: int) -> bool:
    return mavat_code in PURE_RESIDENTIAL_CODES


def is_ambiguous_code(mavat_code: int) -> bool:
    return mavat_code in AMBIGUOUS_CODES
