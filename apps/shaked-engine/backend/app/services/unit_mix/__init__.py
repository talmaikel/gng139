"""B15 · dynamic unit-mix optimisation.

This package consumes existing Shaked Engine inputs (verified per-apartment
areas, buildable area/economic assumptions, and room-level market prices).
It does not scrape or re-derive those inputs.
"""

from app.services.unit_mix.optimizer import optimize_unit_mix
from app.services.unit_mix.schemas import (
    HerzliyaMixPolicy,
    UnitMixCandidate,
    UnitMixOptimizationInput,
    UnitMixOptimizationResult,
    UnitTypeOption,
)

__all__ = [
    "HerzliyaMixPolicy",
    "UnitMixCandidate",
    "UnitMixOptimizationInput",
    "UnitMixOptimizationResult",
    "UnitTypeOption",
    "optimize_unit_mix",
]
