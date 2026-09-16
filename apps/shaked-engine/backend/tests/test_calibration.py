"""‏16.09 · בדיקת אמת מול דוחות 0 אמיתיים של יזם בהרצליה.

שלושה דוחות נמסרו (הקבצים אינם בגיט — יש בהם שמות משפחות). שניים מהם
נושאים כתובת, ולכן אפשר להזין למחשבון את הקלטים שלהם ולהשוות לשורה
התחתונה של הדוח, ״רווחיות מעלויות״. בדיקה שנופלת כאן אומרת שהמודל סטה
מהמציאות, לא שהפרויקט השתנה.

הדוחות מציגים מימון 0 (ריבית 4% רשומה בצד), ולכן גם כאן; ההשבחה נלקחת
מהדוח עצמו (שווי זכויות 12,000 ₪ × השטח שנוסף × רבע), כי המחשבון לבדו
אינו יודע אותה.
"""
import pytest

from app.services.economic.calculator import calculate_feasibility as calc
from app.services.economic.schemas import FeasibilityInput as FI


def test_golomb_17_reads_close_to_its_report():
    """גולומב 17 (גוש 6536 חלקה 741): מגרש 1,464 מ״ר, 8 דירות של 95 מ״ר,
    ‏3,400 מ״ר ברוטו (בדיוק 400% × 850), 36,000 ₪ לדירה טיפוסית, בנייה 7,000.
    בדוח: **16.5%**, אחרי היטל השבחה של 5.7 מיליון (רבע מ-22.9 מיליון)."""
    r = calc(FI(plot_area_sqm=1464, existing_units=8, buildable_area_sqm=3400,
                sale_price_per_sqm=36_000, construction_cost_per_sqm=7_000,
                average_existing_unit_sqm=95, finance_ratio=0.0,
                betterment_base_ils=22_896_000))
    assert 0.13 < r.profit_margin_on_cost_ratio < 0.20, r.profit_margin_on_cost_ratio
    # החלוקה בין היזם לבעלים כמו בדוח: כ-65% ליזם
    assert 0.60 < r.developer_allocation_sqm / r.sellable_main_sqm < 0.70


def test_leib_yaffe_13_reads_close_to_its_report():
    """לייב יפה 13 (גוש 6536 חלקה 536): מגרש 711 מ״ר, 6 דירות של 110 מ״ר,
    ‏2,200 מ״ר ברוטו, 36,000 ₪, בנייה 6,500. בדוח: **6.9%** אחרי היטל של 1.37 מיליון.
    מגרש קטן עם דירות גדולות — גם היזם עצמו מתחת ל-16%."""
    r = calc(FI(plot_area_sqm=711, existing_units=6, buildable_area_sqm=2200,
                sale_price_per_sqm=36_000, construction_cost_per_sqm=6_500,
                average_existing_unit_sqm=110, finance_ratio=0.0,
                betterment_base_ils=5_496_000))
    assert 0.03 < r.profit_margin_on_cost_ratio < 0.12, r.profit_margin_on_cost_ratio
    assert not calc(FI(plot_area_sqm=711, existing_units=6, buildable_area_sqm=2200,
                       sale_price_per_sqm=36_000, construction_cost_per_sqm=6_500,
                       average_existing_unit_sqm=110)).meets_developer_target


def test_the_two_reports_rank_the_same_way_in_the_model():
    """הדוח הגדול רווחי מהקטן — וגם המודל אומר זאת, בפער דומה (כ-10 נקודות)."""
    g = calc(FI(plot_area_sqm=1464, existing_units=8, buildable_area_sqm=3400,
                sale_price_per_sqm=36_000, construction_cost_per_sqm=7_000,
                average_existing_unit_sqm=95))
    l = calc(FI(plot_area_sqm=711, existing_units=6, buildable_area_sqm=2200,
                sale_price_per_sqm=36_000, construction_cost_per_sqm=6_500,
                average_existing_unit_sqm=110))
    assert g.profit_margin_on_cost_ratio - l.profit_margin_on_cost_ratio == pytest.approx(0.10, abs=0.06)
