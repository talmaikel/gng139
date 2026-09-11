from fastapi import APIRouter

from app.core.schemas import UserCreate, UserRead, UserUpdate
from app.core.security import auth_backend, fastapi_users

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/jwt")
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))
router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users")
