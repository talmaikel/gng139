import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, InvalidPasswordException, UUIDIDMixin, exceptions
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.models.tenant import User
from app.services.email import send_password_reset, send_verification

settings = get_settings()


async def get_user_db(session: AsyncSession = Depends(get_async_session)) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def validate_password(self, password: str, user) -> None:
        if len(password) < 8:
            raise InvalidPasswordException(reason="הסיסמה צריכה להיות באורך 8 תווים לפחות.")
        if password.lower() == str(user.email).lower():
            raise InvalidPasswordException(reason="הסיסמה אינה יכולה להיות כתובת הדואר.")

    # ── מיילים ──
    # ‏FastAPI-Users מייצר את הטוקנים ובודק אותם; כאן רק שולחים. טוקן איפוס
    # כולל טביעה של הסיסמה הנוכחית, ולכן קישור ישן מת ברגע שהסיסמה שונתה.

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        # נרשם חדש מקבל מייל אימות מיד. לא חוסם דבר: הוא כבר מחובר.
        try:
            await self.request_verify(user, request)
        except (exceptions.UserAlreadyVerified, exceptions.UserInactive):
            pass

    async def on_after_forgot_password(self, user: User, token: str, request: Request | None = None) -> None:
        await send_password_reset(user.email, token)

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None) -> None:
        await send_verification(user.email, token)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/v1/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=settings.jwt_lifetime_seconds)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
# אדמין של המערכת (צוות שקדן), לא owner של חברת לקוח. נקבע רק מהשרת:
# ‏`scripts/make_admin.py`.
current_superuser = fastapi_users.current_user(active=True, superuser=True)
