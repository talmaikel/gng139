"""כניסה והרשמה.

‏**אין כאן את נתיב ההרשמה של FastAPI-Users.** הוא קיבל מהגולש גם
‏`company_id` וגם `role`, כך שמי שהשיג מזהה של חברה יכול היה להירשם אליה
כ-owner ולקרוא את התיקים שלה. ‏`/signup` שלמטה פותח **חברה חדשה** בכל
הרשמה, והשרת — לא הגולש — קובע לאיזו חברה המשתמש שייך ובאיזה תפקיד.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users import exceptions
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.rate_limit import (email_account_limit, email_ip_limit, login_account_limit,
                                 login_ip_limit, signup_ip_limit)
from app.core.schemas import UserCreate, UserRead, UserUpdate
from app.core.security import UserManager, auth_backend, fastapi_users, get_jwt_strategy, get_user_manager
from app.models.tenant import Company

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/jwt",
                      dependencies=[Depends(login_ip_limit), Depends(login_account_limit)])
router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users")
# ‏forgot-password עונה 202 גם למייל שאינו רשום — אין דרך לברר מי לקוח שלנו.
router.include_router(fastapi_users.get_reset_password_router(),
                      dependencies=[Depends(email_ip_limit), Depends(email_account_limit)])
router.include_router(fastapi_users.get_verify_router(UserRead),
                      dependencies=[Depends(email_ip_limit), Depends(email_account_limit)])


class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str


class SignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(signup_ip_limit)])
async def signup(
    body: SignupRequest,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
) -> SignupResponse:
    """לקוח חדש: חברה חדשה, והנרשם הוא ה-owner שלה.

    החברה מתחילה **בלי זכאות** — יתרה נוצרת ריקה במסירה הראשונה
    (`account._balance`), כך שהרשמה לבדה אינה נותנת תיק.

    החברה והמשתמש נכנסים באותה טרנזקציה: ‏`user_manager.create` מקמט את
    שניהם יחד, ואם המייל תפוס או הסיסמה נדחית — שום דבר לא קומט, והחברה
    נעלמת עם סגירת הסשן.
    """
    company = Company(name=body.company_name.strip(), slug=f"c-{uuid.uuid4().hex[:12]}")
    session.add(company)
    await session.flush()

    try:
        user = await user_manager.create(
            UserCreate(
                email=body.email,
                password=body.password,
                full_name=body.full_name.strip(),
                role="owner",
                company_id=company.id,
            ),
            safe=True,
        )
    except exceptions.UserAlreadyExists:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="כבר קיים חשבון עם כתובת הדואר הזו.")
    except exceptions.InvalidPasswordException as exc:
        await session.rollback()
        raise HTTPException(422, detail=exc.reason)

    token = await get_jwt_strategy().write_token(user)
    return SignupResponse(access_token=token)
