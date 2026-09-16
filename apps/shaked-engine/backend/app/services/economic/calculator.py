"""
Financial feasibility calculator ("Generic Report 0" -- Shaked PRD section 6.4).

Pure Python, no Excel/COM runtime: projects revenue and expense for an
urban-renewal project, splits the new building between existing tenants
(compensation) and the developer (sellable), and returns the profit margin
on cost (PRD requirement ECO-01).

Per the PRD, this tool explicitly is NOT a signed appraiser's report, does
not determine final rights or approved feasibility, and must never present
an estimated figure as a verified one -- callers (see app/worker.py) are
responsible for only invoking this with a substantiated buildable area, and
for surfacing which inputs are data vs. estimate vs. missing.

‏**16.09.2026 · הכיול לפי שלושה דוחות 0 אמיתיים של יזם בהרצליה** (דוח ללא
כתובת · גולומב 17 · לייב יפה 13; הקבצים אינם בגיט — יש בהם שמות משפחות).

1. *הגדרת הרווח.* השורה התחתונה בדוח, ״רווחיות מעלויות״, היא רווח חלקי
   עלויות, כשדירות הבעלים **אינן** הכנסה ו**אינן** עלות. הגרסה הקודמת
   ספרה אותן בשני הצדדים (״הקרקע במכנה״): הרווח בשקלים לא השתנה, אבל
   המכנה כמעט הוכפל, ו-16% שלנו היה רף כפול מ-16% של היזם. גולומב 17 —
   ‏16.5% בדוח — יצא אצלנו 10.4%. עכשיו המדידה היא של הדוח, והרווח היזמי
   המזערי של בועז (16%) מתייחס לאותה שורה.

2. *מה נמכר.* הכנסה מהשטח העיקרי בלבד (תקרת ה-400% כוללת שירות וממ״ד,
   §70ב(א)(1)), ועכשיו גם מרפסת של 12 מ״ר לדירה חדשה בחצי מחיר — כפי
   שהדוחות מתמחרים (״מחיר למ״ר אקוויוולנטי״).

3. *שורות שלא היו ושורות שהוגזמו.* נוספו אגרות בנייה, מס רכישה על זכויות
   היזם, יועצים לדירה, תב״ע, מפקח דיירים ועמלות בנק. הריסה היא לבניין
   ולא לדירה, המימון 4% ולא 6%, והחניון 60% מהברוטו ולא 40%.

The betterment levy is half-known and the model says which half.
Amendment 139 added §19(ב)(10א) to the Third Schedule and set **a quarter
of the betterment** for a plan under סימן ד׳ — not the standard half. That
rate is DATA. The betterment itself, the rise in land value the plan
causes, is a valuation and stays MISSING, so a scenario that ignores it
still cannot be reported as deliverable.
"""

from app.services.economic.schemas import FeasibilityInput, FeasibilityResult


def calculate_feasibility(inputs: FeasibilityInput,
                          missing_inputs: list[str] | None = None) -> FeasibilityResult:
    """Run the scenario.

    `missing_inputs` names the commercial inputs that are genuinely unknown
    (see `EconomicAssumptionSet.blocking`). The numbers are still computed --
    a scenario built on a placeholder is useful to reason with -- but the
    result carries `is_deliverable=False`, so it cannot be handed to a client
    as though it rested on data.

    B15 may pass `developer_sale_revenue_ils`: the exact revenue of the
    enumerated developer apartments. In that case Report 0 keeps the same
    cost model and stops valuing unused residual area as though it were
    another apartment for sale. That revenue already prices whole
    apartments, balconies included, so no balcony revenue is added to it.
    """
    # ── שטחים ──
    sellable_main_sqm = inputs.buildable_area_sqm * inputs.main_area_ratio
    underground_sqm = inputs.buildable_area_sqm * inputs.underground_ratio
    constructed_area_sqm = inputs.buildable_area_sqm + underground_sqm

    tenant_requirement_sqm = inputs.existing_units * (
        inputs.average_existing_unit_sqm + inputs.tenant_compensation_sqm_per_existing_unit
    )
    tenants_fit = tenant_requirement_sqm <= sellable_main_sqm
    tenant_allocation_sqm = min(tenant_requirement_sqm, sellable_main_sqm)
    developer_allocation_sqm = sellable_main_sqm - tenant_allocation_sqm
    developer_share = developer_allocation_sqm / sellable_main_sqm if sellable_main_sqm > 0 else 0.0

    # מספר הדירות החדשות, לאומדן מרפסות ויועצים: לא פחות מהדירות הקיימות,
    # כי כל בעלים מקבל דירה.
    # עיגול חצי כלפי מעלה, כמו ROUND באקסל — ולא עיגול הבנקאים של פייתון.
    new_units_estimate = max(int(sellable_main_sqm / inputs.average_new_unit_sqm + 0.5),
                             inputs.existing_units, 1)
    balcony_sqm = new_units_estimate * inputs.balcony_sqm_per_new_unit

    # ── הכנסות, נטו ממע״מ ──
    # מחיר שוק מצוטט כולל מע״מ ועלויות מוצגות נטו. בלי היישור הזה המרווח
    # מנופח בשיעור המע״מ מיד, לפני כל שורת עלות חסרה.
    net_price = (inputs.sale_price_per_sqm / (1 + inputs.vat_rate)
                 if inputs.sale_price_includes_vat else inputs.sale_price_per_sqm)
    # דירות הבעלים: התמורה על הקרקע. מוצגות, ואינן במכנה.
    owners_flats_value_ils = tenant_allocation_sqm * net_price

    if inputs.developer_sale_revenue_ils is None:
        balcony_revenue_ils = balcony_sqm * developer_share * inputs.balcony_price_factor * net_price
        developer_revenue_ils = developer_allocation_sqm * net_price + balcony_revenue_ils
    else:
        balcony_revenue_ils = 0.0
        developer_revenue_ils = (
            inputs.developer_sale_revenue_ils / (1 + inputs.vat_rate)
            if inputs.sale_price_includes_vat
            else inputs.developer_sale_revenue_ils
        )
    total_revenue_ils = developer_revenue_ils

    # ── עלויות ──
    total_construction_cost_ils = inputs.buildable_area_sqm * inputs.construction_cost_per_sqm
    total_underground_cost_ils = underground_sqm * inputs.underground_cost_per_sqm
    total_balcony_cost_ils = balcony_sqm * inputs.balcony_cost_per_sqm
    direct_cost_ils = total_construction_cost_ils + total_underground_cost_ils + total_balcony_cost_ils
    total_soft_cost_ils = direct_cost_ils * inputs.soft_cost_ratio
    total_demolition_cost_ils = inputs.demolition_cost_ils
    total_tenant_cost_ils = inputs.existing_units * (
        inputs.tenant_rent_months * inputs.tenant_monthly_rent_ils
        + inputs.tenant_moving_cost_ils
        + inputs.tenant_legal_cost_per_unit_ils
    ) + inputs.tenants_supervisor_ils
    total_consultants_ils = new_units_estimate * inputs.consultants_per_new_unit_ils + inputs.plan_cost_ils
    total_fees_ils = constructed_area_sqm * inputs.permit_fee_per_sqm
    purchase_tax_ils = inputs.purchase_tax_ratio * inputs.rights_value_per_sqm_ils * developer_allocation_sqm
    # ‏**E1 · 15.09 (בועז) — שיווק אינו מחושב על דירות הבעלים.** ערבויות
    # נשארות על הכול: היזם נותן ערבויות חוק מכר גם לבעלים.
    total_marketing_ils = developer_revenue_ils * inputs.marketing_ratio
    total_guarantees_ils = (developer_revenue_ils + owners_flats_value_ils) * inputs.guarantees_ratio
    # רבע מההשבחה, ולא אחוז מההכנסות. הבסיס הוא שומה ולא נגזרת של המכירה.
    betterment_levy_ils = inputs.betterment_base_ils * inputs.betterment_levy_rate

    # עמלות בנק ומימון נגזרים מכל השאר, ולכן מחושבים אחרונים ואינם נכנסים
    # לבסיס של עצמם.
    cost_before_finance = (total_construction_cost_ils + total_underground_cost_ils
                           + total_balcony_cost_ils + total_soft_cost_ils
                           + total_demolition_cost_ils + total_tenant_cost_ils
                           + total_consultants_ils + total_fees_ils + purchase_tax_ils
                           + total_marketing_ils + total_guarantees_ils
                           + betterment_levy_ils)
    total_bank_fees_ils = cost_before_finance * inputs.bank_fees_ratio
    total_finance_ils = cost_before_finance * inputs.finance_ratio
    total_cost_ils = cost_before_finance + total_bank_fees_ils + total_finance_ils

    projected_profit_ils = total_revenue_ils - total_cost_ils
    profit_margin_on_cost_ratio = (projected_profit_ils / total_cost_ils) if total_cost_ils > 0 else 0.0

    r = round
    return FeasibilityResult(
        sellable_main_sqm=r(sellable_main_sqm, 2),
        tenant_allocation_sqm=r(tenant_allocation_sqm, 2),
        developer_allocation_sqm=r(developer_allocation_sqm, 2),
        constructed_area_sqm=r(constructed_area_sqm, 2),
        balcony_sqm=r(balcony_sqm, 2),
        new_units_estimate=new_units_estimate,
        total_revenue_ils=r(total_revenue_ils, 2),
        developer_revenue_ils=r(developer_revenue_ils, 2),
        balcony_revenue_ils=r(balcony_revenue_ils, 2),
        owners_flats_value_ils=r(owners_flats_value_ils, 2),
        total_construction_cost_ils=r(total_construction_cost_ils, 2),
        total_underground_cost_ils=r(total_underground_cost_ils, 2),
        total_balcony_cost_ils=r(total_balcony_cost_ils, 2),
        total_soft_cost_ils=r(total_soft_cost_ils, 2),
        total_demolition_cost_ils=r(total_demolition_cost_ils, 2),
        total_tenant_cost_ils=r(total_tenant_cost_ils, 2),
        total_consultants_ils=r(total_consultants_ils, 2),
        total_fees_ils=r(total_fees_ils, 2),
        purchase_tax_ils=r(purchase_tax_ils, 2),
        total_marketing_ils=r(total_marketing_ils, 2),
        total_guarantees_ils=r(total_guarantees_ils, 2),
        total_bank_fees_ils=r(total_bank_fees_ils, 2),
        total_finance_ils=r(total_finance_ils, 2),
        betterment_levy_ils=r(betterment_levy_ils, 2),
        total_cost_ils=r(total_cost_ils, 2),
        projected_profit_ils=r(projected_profit_ils, 2),
        profit_margin_on_cost_ratio=r(profit_margin_on_cost_ratio, 4),
        meets_developer_target=profit_margin_on_cost_ratio >= inputs.developer_profit_target_ratio,
        tenants_fit=tenants_fit,
        inputs_missing=sorted(missing_inputs or []),
        is_deliverable=not missing_inputs,
    )
