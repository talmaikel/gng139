from fastapi import APIRouter, Depends

from app.core.security import current_active_user
from app.models.tenant import User
from app.services.economic.calculator import calculate_feasibility
from app.services.economic.schemas import FeasibilityInput, FeasibilityResult

router = APIRouter(prefix="/economic", tags=["economic"])


@router.post("/feasibility", response_model=FeasibilityResult)
async def run_feasibility_scenario(
    inputs: FeasibilityInput,
    user: User = Depends(current_active_user),
) -> FeasibilityResult:
    """Run the 'Generic Report 0' feasibility calculator for a given scenario."""
    return calculate_feasibility(inputs)
