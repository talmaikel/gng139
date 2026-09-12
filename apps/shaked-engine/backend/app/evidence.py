"""
Per-field evidence.

Every value the Engine holds about a property is an observation: the value, the
source it was read from, when it was retrieved, where in that source it sits,
how it was read, and how far it can be trusted. A field is then resolved from
all of its observations.

Ported from POC/app/rules.py (evidence, resolve_evidence, usable) with the rules
unchanged, because they carry guarantees the POC's tests pin down:

- competing observations are kept; a disagreement never silently picks one
- only official, derived or manually verified values can decide a check
- a value with no source URL, retrieval time or location decides nothing
- a value older than the freshness window decides nothing

Observations are plain dicts in the POC's shape, so the eligibility rules can be
ported next without rewriting how they read fields. Storage is the
field_evidence table (app/models/evidence.py).
"""

import enum
import json
from datetime import datetime, timezone
from typing import Any

SOURCE_MAX_AGE_DAYS = 30

# The resolved state of a field whose observations disagree. It describes a
# field, never a single observation, so it is not a Certainty and is not stored.
CONFLICT = "conflict"


class Certainty(str, enum.Enum):
    OFFICIAL = "official"                    # read from an authoritative public record
    DERIVED = "derived"                      # computed from official inputs, e.g. a polygon area
    MANUALLY_VERIFIED = "manually_verified"  # confirmed by a person against the document
    COMMUNITY = "community"                  # e.g. OpenStreetMap: good for discovery, never decides
    OCR_CANDIDATE = "ocr_candidate"          # machine-read from a scan, awaiting human review
    AI_CANDIDATE = "ai_candidate"            # model-read, awaiting human review (see pipeline/extractor.py)
    MISSING = "missing"                      # looked for and not found


DECIDING = frozenset({Certainty.OFFICIAL.value, Certainty.DERIVED.value, Certainty.MANUALLY_VERIFIED.value})


def evidence(
    value: Any,
    source: dict[str, Any] | None = None,
    certainty: Certainty | str = Certainty.MISSING,
    location: str | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    """One observation. `source` carries at least `url` and `retrieved_at` (ISO 8601)."""
    return {
        "value": value,
        "certainty": Certainty(certainty).value,
        "source": source,
        "location": location,
        "method": method,
    }


def resolve_evidence(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Resolve one field from everything observed about it. Agreement yields the
    value; disagreement yields a conflict that keeps every observation.
    """
    present = [o for o in observations if o.get("value") is not None]
    if not present:
        return evidence(None)
    distinct = {json.dumps(o["value"], sort_keys=True, ensure_ascii=False) for o in present}
    if len(distinct) > 1:
        return {**evidence(None), "certainty": CONFLICT, "observations": present}
    return {**present[0], "observations": present}


def usable(
    field: dict[str, Any] | None,
    max_age_days: int = SOURCE_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> bool:
    """Whether an observation, or a resolved field, may decide an eligibility check."""
    if not field or field.get("value") is None or field.get("certainty") not in DECIDING:
        return False
    source = field.get("source") or {}
    if not source.get("url") or not source.get("retrieved_at"):
        return False
    try:
        retrieved = datetime.fromisoformat(source["retrieved_at"])
        age_days = ((now or datetime.now(timezone.utc)) - retrieved).total_seconds() / 86400
    except (TypeError, ValueError):
        # Unparseable or timezone-naive retrieval times cannot be aged, so they decide nothing.
        return False
    return 0 <= age_days <= max_age_days and field.get("location") is not None
