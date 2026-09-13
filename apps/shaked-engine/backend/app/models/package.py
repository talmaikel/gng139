import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Package(Base):
    """A purchasable bundle of opportunity credits sold to a tenant company."""

    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    price_ils: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Balance(Base):
    """Remaining opportunity credits for a tenant company."""

    __tablename__ = "balances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    credits_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReservationStatus(str, enum.Enum):
    ACTIVE = "active"      # lock currently held, opportunity hidden from other tenants
    RELEASED = "released"  # lock voluntarily released or expired
    CONVERTED = "converted"  # lock converted into a purchased dossier


class Reservation(Base):
    """
    Prospective lock on an opportunity, preventing the same parcel from being
    served to a competing tenant while due-diligence / dossier generation is active.
    """

    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ReservationStatus.ACTIVE,
        nullable=False,
    )
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Only one ACTIVE reservation may exist per opportunity at a time, so a locked
        # parcel cannot be handed to a second, competing tenant while the lock holds.
        Index(
            "ux_reservations_active_opportunity",
            "opportunity_id",
            unique=True,
            postgresql_where="status = 'active'",
        ),
    )


class Delivery(Base):
    """One opportunity handed to one company. Permanent, and the record that
    makes entitlement mean something.

    ‏`Reservation` הוא נעילה זמנית וגלובלית — חברה אחת מחזיקה מגרש ואחרות
    אינן רואות אותו. הוא **אינו** רישום מסירה, ובלי רישום מסירה שתי הדרישות
    המרכזיות של ה-PRD חסרות משמעות:

      **SEL-02** · *״אותו מגרש אינו נספר שוב בעקבות פוליגון חופף, שינוי
      כתובת, שינוי משתמש בחברה או חבילה חדשה. מגרש שכבר נמסר מוצג במאגר
      החברה בלבד ואינו צורך זכאות נוספת.״*

      **ACC-04** · *״שני משתמשים באותה חברה סורקים פוליגונים חופפים: אותה
      הזדמנות נמסרת פעם אחת.״*

    ‏**הבעלות היא של החברה ולא של המשתמש** — ה-PRD מפורש: *״תוצאה שנמסרה
    למשתמש בחברה נחשבת תוצאה שנמסרה לחברה״*. לכן האילוץ הייחודי הוא על
    ‏(opportunity, company), ו-`delivered_to_user_id` הוא תיעוד בלבד: החלפת
    משתמש בחברה אינה מזכה במסירה חוזרת.

    ‏**המסירה שורדת שריון של אחר** (ACC-06: *״חברה א׳ קיבלה תיק לפני שחברה
    ב׳ הפעילה שריון: א׳ שומרת גישה״*). אין כאן שדה סטטוס וגם לא צריך —
    שורה שנכתבה אינה נמחקת.
    """

    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # מי ביקש, לתיעוד. הזכאות היא של החברה, ולכן זה אינו חלק מהמפתח.
    delivered_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ‏1 במסירה הראשונה, 0 בכל חזרה. ‏ACC-05: מועמד לא מוכן אינו מגיע לכאן
    # כלל, ולכן אינו צורך יתרה.
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ‏SEL-01: *״נשמרים גרסת הנתונים, גרסת הכללים והנימוק לכל בחירה״*.
    # בלי אלה אי אפשר לענות ללקוח למה דווקא המגרש הזה נבחר לפני חצי שנה.
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    data_version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    why_selected: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        # לב SEL-02. פוליגון חופף, כתובת שהשתנתה, משתמש אחר או חבילה חדשה —
        # כולם מגיעים לאותה שורה, והאילוץ הוא זה שהופך את הדרישה לאמיתית.
        UniqueConstraint("opportunity_id", "company_id", name="ux_deliveries_company_opportunity"),
        Index("ix_deliveries_company", "company_id"),
    )
