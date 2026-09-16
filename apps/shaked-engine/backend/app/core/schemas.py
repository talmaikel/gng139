import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    full_name: str
    role: str
    company_id: uuid.UUID


class UserCreate(schemas.BaseUserCreate):
    """פנימי בלבד — נבנה בשרת ב-`/auth/signup`, לא נקלט מהגולש כמו שהוא."""
    full_name: str
    role: str = "member"
    company_id: uuid.UUID


class UserUpdate(schemas.BaseUserUpdate):
    # ‏בלי `role`: ‏`PATCH /auth/users/me` מקבל את הסכמה הזו, ומשתמש רגיל
    # היה מעלה את עצמו ל-owner.
    full_name: str | None = None
