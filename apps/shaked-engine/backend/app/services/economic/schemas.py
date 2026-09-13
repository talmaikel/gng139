from pydantic import BaseModel, Field


class FeasibilityInput(BaseModel):
    """Inputs to the 'Generic Report 0' financial feasibility calculator.

    Every field is an explicit, named input. Nothing here may be a bare
    magic number: `app.services.economic.assumptions` is the library that
    supplies them, carries their date and version, and marks each one
    data / estimate / missing (PRD ECO-02).
    """

    plot_area_sqm: float = Field(gt=0)
    existing_units: int = Field(ge=0)
    buildable_area_sqm: float = Field(gt=0, description="Total permitted above-ground building area in the NEW building (sqm)")

    sale_price_per_sqm: float = Field(gt=0, description="Expected sale price per sqm of new MAIN area (ILS)")
    construction_cost_per_sqm: float = Field(gt=0, description="Hard construction cost per sqm above ground (ILS)")

    # ── שטח נמכר מול שטח בנוי ──
    # תקרת ה-400% של §70ב(א)(1) כוללת במפורש שטחי שירות וממ״דים. אלה נבנים
    # ואינם נמכרים במחיר דירה, ולכן ההכנסה נגזרת מהשטח העיקרי בלבד.
    main_area_ratio: float = Field(default=0.78, gt=0, le=1,
        description="Share of the permitted area that is main (sellable) area, not service")
    # חניון תת-קרקעי אינו נספר בתקרה אבל כן נבנה ומשולם.
    underground_ratio: float = Field(default=0.40, ge=0,
        description="Underground built area as a ratio of the above-ground permitted area")
    underground_cost_per_sqm: float = Field(default=6_000.0, ge=0)

    soft_cost_ratio: float = Field(default=0.15, ge=0, description="Soft costs (planning/permits/design) as a ratio of construction cost")
    demolition_cost_per_unit: float = Field(default=150_000, ge=0)

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
    tenant_rent_months: float = Field(default=42.0, ge=0, description="Months of rent paid per tenant during construction")
    tenant_monthly_rent_ils: float = Field(default=7_500.0, ge=0)
    tenant_moving_cost_ils: float = Field(default=10_000.0, ge=0, description="Two moves per tenant")
    tenant_legal_cost_per_unit_ils: float = Field(default=30_000.0, ge=0,
        description="Tenants' lawyer and appraiser, paid by the developer")

    # ── שיעורים על ההכנסה ועל העלות ──
    marketing_ratio: float = Field(default=0.025, ge=0, description="Marketing and brokerage, as a ratio of revenue")
    guarantees_ratio: float = Field(default=0.0125, ge=0, description="Sales Law guarantees and insurance, as a ratio of revenue")
    finance_ratio: float = Field(default=0.06, ge=0, description="Bank accompaniment and interest, as a ratio of all other costs")
    betterment_levy_ratio: float = Field(default=0.0, ge=0,
        description="Betterment levy as a ratio of revenue. Whether amendment 139 carries an exemption is UNRESOLVED")

    # ── מע״מ ──
    # מחיר שוק מצוטט כולל מע״מ; עלויות מוצגות נטו. בלי יישור, המרווח מנופח
    # בשיעור המע״מ מיד, לפני כל שורת עלות חסרה.
    sale_price_includes_vat: bool = True
    vat_rate: float = Field(default=0.18, ge=0)

    developer_profit_target_ratio: float = Field(
        default=0.20, ge=0, description="Developer's minimum required profit-on-cost ratio (see PRD ECO-01)"
    )


class FeasibilityResult(BaseModel):
    """Output of the feasibility calculator, as pure JSON — no Excel runtime involved."""

    # ── שטחים ──
    sellable_main_sqm: float
    tenant_allocation_sqm: float
    developer_allocation_sqm: float
    constructed_area_sqm: float

    # ── הכנסות ──
    # ‏`total_revenue_ils` הוא שווי כל השטח הנמכר בבניין, כולל דירות הדיירים.
    # הן יוצאות שוב כ-`land_cost_ils`, כי פיצוי הדיירים **הוא** התמורה על
    # הקרקע. זו צורת ההצגה של דוח אפס, והיא זו שנותנת מכנה בעל משמעות
    # ל״רווח על העלות״ — הגרסה הקודמת החזיקה את התשומה הגדולה ביותר מחוץ
    # למכנה והחזירה 305%.
    total_revenue_ils: float
    developer_revenue_ils: float

    # ── עלויות ──
    land_cost_ils: float
    total_construction_cost_ils: float
    total_underground_cost_ils: float
    total_soft_cost_ils: float
    total_demolition_cost_ils: float
    total_tenant_cost_ils: float
    total_marketing_ils: float
    total_guarantees_ils: float
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
