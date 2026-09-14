"""Assumptions for estimating existing private/unit area when no verified schedule exists.

These assumptions are intentionally separate from the future-project
``main_area_ratio``.  The latter describes sellable area in a new project;
this module describes a fallback for an existing building when the gramoshka
or apartment schedule is missing.
"""

from dataclasses import dataclass
from datetime import date

from app.services.economic.assumptions import AssumptionStatus


@dataclass(frozen=True)
class ExistingPrivateAreaRatioAssumption:
    value: float
    status: AssumptionStatus
    source: str
    sample_n: int
    recommended_min: float
    recommended_max: float
    effective_date: date


D5_EXISTING_PRIVATE_AREA_RATIO = ExistingPrivateAreaRatioAssumption(
    value=0.85,
    status=AssumptionStatus.ESTIMATE,
    source=(
        "D5 preliminary calibration: 3 residential permit records; "
        "main/(main+service), above-ground residential only; "
        "mean=84.49%, median=84.62%, range=80.79%-88.08%. "
        "Not yet validated on 3-5 Herzliya gramushkas."
    ),
    sample_n=3,
    recommended_min=0.80,
    recommended_max=0.90,
    effective_date=date(2026, 9, 14),
)
