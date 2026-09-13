from fastapi import APIRouter

from app.api.v1 import account, auth, candidates, dossiers, economic, filters

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(candidates.router)
api_router.include_router(filters.router)
api_router.include_router(dossiers.router)
api_router.include_router(economic.router)
api_router.include_router(account.router)
