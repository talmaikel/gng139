import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    full_name: str
    role: str
    company_id: uuid.UUID


class UserCreate(schemas.BaseUserCreate):
    full_name: str
    role: str = "member"
    company_id: uuid.UUID


class UserUpdate(schemas.BaseUserUpdate):
    full_name: str | None = None
    role: str | None = None
