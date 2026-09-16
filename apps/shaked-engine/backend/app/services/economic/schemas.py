from pydantic import BaseModel, Field


class FeasibilityInput(BaseModel):
    """Inputs to the 'Generic Report 0' financial feasibility calculator.

    Every field is an explicit, named input. Nothing here may be a bare
    magic number: `app.services.economic.assumptions` is the library that
    supplies them, carries their date and version, and marks each one
    data / estimate / missing (PRD ECO-02).

    ‏**16.09.2026 · הכיול לפי שלושה דוחות 0 של יזם בהרצליה.** ברירות המחדל
    כאן הן של הדוחות: שטח עיקרי 85%, חניון 60%, הריסה לבניין, מימון 4% ועוד
    עמלות בנק, ושורות שלא היו — מרפסות, אגרות בנייה, מס רכישה, יועצים, תב״ע.
    """

    plot_area_sqm: float = Field(gt=0)
    existing_units: int = Field(ge=0)
    buildable_area_sqm: float = Field(gt=0, description="Total permitted above-ground building area in the NEW building (sqm)")

    sale_price_per_sqm: float = Field(gt=0, description="Expected sale price per sqm of new MAIN area (ILS)")
    construction_cost_per_sqm: float = Field(gt=0, description="Hard construction cost per sqm above ground (ILS)")

    # B15 may know the exact revenue of the enumerated developer apartments
    # (room-sensitive price x apartment area x count). When supplied, Report 0
    # uses it instead of pretending every residual sqm sells at one blended
    # price. The amount follows sale_price_includes_vat, and it already prices
    # whole apartments — balconies included — so no balcony revenue is added.
    developer_sale_revenue_ils: float | None = Field(
        default=None,
        ge=0,
        description="Exact market value of developer-sale apartments; optional B15 override",
    )

    # ── שטח נמכר מול שטח בנוי ──
    # תקרת ה-400% של §70ב(א)(1) כוללת במפורש שטחי שירות וממ״דים. אלה נבנים
    # ואינם נמכרים במחיר דירה, ולכן ההכנסה נגזרת מהשטח העיקרי בלבד.
    # ‏85%: בשלושת הדוחות העיקרי הוא 82%–90% מהברוטו (היה 78%).
    main_area_ratio: float = Field(default=0.85, gt=0, le=1,
        description="Share of the permitted area that is main (sellable) area, not service")
    # חניון תת-קרקעי אינו נספר בתקרה אבל כן נבנה ומשולם. בדוחות: שתי קומות
    # מרתף על 90% מהמגרש — 56%–77% מהברוטו (היה 40%).
    underground_ratio: float = Field(default=0.60, ge=0,
        description="Underground built area as a ratio of the above-ground permitted area")
    underground_cost_per_sqm: float = Field(default=3_900.0, ge=0)

    # ── מרפסות ──
    # בדוחות כל דירה חדשה מקבלת מרפסת של 12 מ״ר שאינה בשטח המותר (§2ו), נבנית
    # ב-2,500 ₪ למ״ר, ונמכרת בחצי מחיר מ״ר עיקרי (״מחיר למ״ר אקוויוולנטי״).
    balcony_sqm_per_new_unit: float = Field(default=12.0, ge=0)
    balcony_price_factor: float = Field(default=0.5, ge=0, le=1,
        description="Share of the main-area price a balcony sqm sells for")
    balcony_cost_per_sqm: float = Field(default=2_500.0, ge=0)
    # לאומדן מספר הדירות החדשות כשאין תמהיל: שטח עיקרי ÷ דירה ממוצעת.
    average_new_unit_sqm: float = Field(default=100.0, gt=0)

    soft_cost_ratio: float = Field(default=0.15, ge=0,
        description="Overhead, supervision, contingency and legal, as a ratio of direct construction")
    # הריסה היא לבניין ולא לדירה: ״הריסת מבנה קיים · קומפלט · 250,000״ בשלושת הדוחות.
    demolition_cost_ils: float = Field(default=250_000, ge=0)

    # Deliberately NOT derived from buildable_area_sqm / existing_units: that
    # would always consume exactly 100% of the new building regardless of its
    # size, leaving the developer with zero share by construction. Tenant
    # compensation must be sized off the OLD building being replaced.
    average_existing_unit_sqm: float = Field(
        default=70.0, gt=0, description="Assumed average size of an existing apartment being replaced (sqm)"
    )
    tenant_compensation_sqm_per_existing_unit: float = Field(
        default=25.0, ge=0, description="Extra sqm of new apartment granted to each existing tenant, beyond a 1:1 replacement"
    )

    # ── עלויות הדיירים, שכולן על היזם ──
    tenant_rent_months: float = Field(default=36.0, ge=0, description="Months of rent paid per tenant during construction")
    tenant_monthly_rent_ils: float = Field(default=7_500.0, ge=0)
    tenant_moving_cost_ils: float = Field(default=16_000.0, ge=0, description="Two moves per tenant")
    tenant_legal_cost_per_unit_ils: float = Field(default=30_000.0, ge=0,
        description="Tenants' lawyer and appraiser, paid by the developer")
    tenants_supervisor_ils: float = Field(default=250_000.0, ge=0,
        description="The tenants' own supervising engineer, paid by the developer")

    # ── תכנון, אגרות ומיסים ──
    consultants_per_new_unit_ils: float = Field(default=50_000.0, ge=0,
        description="Architect, engineers and consultants, per new apartment")
    plan_cost_ils: float = Field(default=150_000.0, ge=0, description="The point plan (תב״ע)")
    permit_fee_per_sqm: float = Field(default=300.0, ge=0,
        description="Municipal building-permit fees, per sqm above and below ground")
    # מס רכישה: היזם רוכש את זכויות הבנייה שלו מהבעלים. הבסיס הוא שווי
    # מ״ר זכויות, והדוחות מניחים 12,000 ₪ (״אופציה ב״).
    purchase_tax_ratio: float = Field(default=0.06, ge=0, le=1)
    rights_value_per_sqm_ils: float = Field(default=12_000.0, ge=0,
        description="Assumed value of one sqm of building rights, the purchase-tax base")

    # ── שיעורים על ההכנסה ועל העלות ──
    marketing_ratio: float = Field(default=0.015, ge=0, description="Marketing and brokerage, as a ratio of developer revenue")
    guarantees_ratio: float = Field(default=0.0125, ge=0,
        description="Sales Law guarantees and insurance, as a ratio of developer revenue plus the owners' flats")
    bank_fees_ratio: float = Field(default=0.013, ge=0,
        description="Credit-allocation and accompaniment fees, as a ratio of costs before finance")
    finance_ratio: float = Field(default=0.04, ge=0, description="Interest on the bank accompaniment, as a ratio of costs before finance")
    # ‏§19(ב)(10א)(א) לתוספת השלישית, שנוסף בתיקון 139: **רבע ההשבחה**
    # לתכנית לפי סימן ד׳, ולא מחצית. השיעור ידוע; ההשבחה עצמה — עליית
    # שווי המקרקעין בשל התכנית — היא שומה, ולכן היא קלט נפרד.
    betterment_levy_rate: float = Field(default=0.25, ge=0, le=1,
        description="Statutory rate on the betterment — a quarter under amendment 139")
    betterment_base_ils: float = Field(default=0.0, ge=0,
        description="The betterment itself (rise in land value from the plan). Needs an appraiser")

    # ── מע״מ ──
    # מחיר שוק מצוטט כולל מע״מ; עלויות מוצגות נטו. בלי יישור, המרווח מנופח
    # בשיעור המע״מ מיד, לפני כל שורת עלות חסרה.
    sale_price_includes_vat: bool = True
    vat_rate: float = Field(default=0.18, ge=0)

    developer_profit_target_ratio: float = Field(
        default=0.16, ge=0, description="Developer's minimum required profit-on-cost ratio (see PRD ECO-01)"
    )


class FeasibilityResult(BaseModel):
    """Output of the feasibility calculator, as pure JSON — no Excel runtime involved."""

    # ── שטחים ──
    sellable_main_sqm: float
    tenant_allocation_sqm: float
    developer_allocation_sqm: float
    constructed_area_sqm: float
    balcony_sqm: float = 0.0
    new_units_estimate: int = 0

    # ── הכנסות ──
    # ‏**16.09 · ״רווחיות מעלויות״ כמו בדוח 0.** ‏`total_revenue_ils` הוא הכנסות
    # היזם בלבד — הדירות שהוא מוכר, ומרפסותיהן. דירות הבעלים אינן הכנסה
    # ואינן עלות: הן התמורה על הקרקע, ושווין מוצג ב-`owners_flats_value_ils`
    # להשוואה ולערבויות, מחוץ למכנה. הגרסה הקודמת ספרה אותן בשני הצדדים,
    # ו-16% שלנו היה רף כפול מ-16% של היזם.
    total_revenue_ils: float
    developer_revenue_ils: float
    balcony_revenue_ils: float = 0.0
    owners_flats_value_ils: float = 0.0

    # ── עלויות ──
    total_construction_cost_ils: float
    total_underground_cost_ils: float
    total_balcony_cost_ils: float = 0.0
    total_soft_cost_ils: float
    total_demolition_cost_ils: float
    total_tenant_cost_ils: float
    total_consultants_ils: float = 0.0
    total_fees_ils: float = 0.0
    purchase_tax_ils: float = 0.0
    total_marketing_ils: float
    total_guarantees_ils: float
    total_bank_fees_ils: float = 0.0
    total_finance_ils: float
    betterment_levy_ils: float
    total_cost_ils: float

    projected_profit_ils: float
    # profit / cost (not / revenue) -- PRD 6.4 ECO-01: "שיעור רווח על העלות
    # הוא ההפרש חלקי ההוצאות" ("profit rate on cost is the difference
    # divided by expenses"), computed only when cost is positive.
    profit_margin_on_cost_ratio: float
    meets_developer_target: bool

    # Whether the new building can house the existing tenants at all. Without
    # it, an impossible project reports as an ordinary loss: 60 tenants in a
    # 3,396 sqm building returned a developer share of 0 and a 40M loss, with
    # nothing saying the replacement itself does not fit.
    tenants_fit: bool = True

    # PRD ECO-02: an estimated figure must never be presented as a verified
    # one. These two carry that from the assumptions library into the result,
    # so the caller cannot lose it by forgetting to look.
    inputs_missing: list[str] = Field(default_factory=list)
    is_deliverable: bool = True
