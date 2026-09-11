from typing import Any

from fastapi import APIRouter, Depends

from app.cities import CITY_REGISTRY
from app.core.security import current_active_user
from app.models.opportunity import VerificationLevel
from app.models.tenant import User

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("/options")
async def get_filter_options(user: User = Depends(current_active_user)) -> dict[str, Any]:
    """Available filter values for the candidates screen (cities, verification levels)."""
    return {
        "cities": [
            {"code": rules.city_code, "name": rules.display_name} for rules in (cls() for cls in CITY_REGISTRY.values())
        ],
        "verification_levels": [level.value for level in VerificationLevel],
    }
