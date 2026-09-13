/** שמות שדות בעברית. המזהים באנגלית כי הם מזהים בקוד — ומה שמוצג לאדם
 *  צריך להיות בשפה שלו, ובמונחים של נדל״ן ולא של בסיס נתונים. */
export const FIELD_LABEL: Record<string, string> = {
  parcel_area: "שטח המגרש",
  units: "מספר דירות קיים",
  floors: "מספר קומות קיים",
  existing_area: "שטח בנוי קיים",
  street_width: "רוחב הרחוב",
  pilotis: "קומת עמודים",
  registration_area: "אזור רישום",
  in_tama70: 'בתחום תמ"א 70',
  scope_buildings: "מספר מבנים בחלקה",
  renewal_policy_category: "קטגוריה במפת המדיניות",
  category_ceiling: "תקרת הקטגוריה",
  residential_zoning: "ייעוד למגורים",
  residential_share: "שיעור השימוש למגורים",
  permit_date: "מועד ההיתר",
  strengthened: "בוצע חיזוק בהיתר",
  occupied: "יוזמה פעילה של אחר",
  post_2005_permit: "היתר אחרי 18.5.2005",
};

export const CERTAINTY_LABEL: Record<string, string> = {
  official: "רשמי",
  derived: "נגזר",
  manually_verified: "אומת ידנית",
  community: "קהילתי",
  ocr_candidate: "קריאת OCR",
  ai_candidate: "קריאת מודל",
  estimate: "אומדן",
  missing: "נבדק ולא נמצא",
  conflict: "סתירה בין מקורות",
};

export const GATE_STATUS: Record<string, { label: string; colour: string; background: string }> = {
  passed: { label: "עבר", colour: "#1f5f55", background: "#eaf4f0" },
  failed: { label: "נכשל", colour: "#a8321e", background: "#fbeeea" },
  unknown: { label: "לא ידוע", colour: "#8a6100", background: "#fbf4e4" },
  routed: { label: "נותב למתחמים", colour: "#1d4e89", background: "#eaf0f9" },
  undefined: { label: "המדיניות שותקת", colour: "#5c5750", background: "#f0efec" },
  needs_measurement: { label: "דורש מדידה", colour: "#8a6100", background: "#fbf4e4" },
};

export const ASSUMPTION_LABEL: Record<string, string> = {
  sale_price_per_sqm_ils: "מחיר מכירה למ״ר",
  construction_cost_per_sqm_ils: "עלות בנייה למ״ר",
  demolition_cost_per_unit_ils: "הריסה ליח״ד",
  soft_cost_ratio: "עלויות רכות",
  developer_profit_target_ratio: "יעד רווח ליזם",
  main_area_ratio: "שיעור השטח העיקרי",
  underground_ratio: "שיעור חניון תת-קרקעי",
  underground_cost_per_sqm_ils: "עלות חניון למ״ר",
  average_existing_unit_sqm: "שטח דירה קיימת ממוצע",
  tenant_compensation_sqm_per_existing_unit: "תוספת לדייר",
  tenant_rent_months: "חודשי שכירות לדיירים",
  tenant_monthly_rent_ils: "שכ״ד חודשי לדייר",
  tenant_moving_cost_ils: "הובלות לדייר",
  tenant_legal_cost_per_unit_ils: "עו״ד ושמאי לדייר",
  marketing_ratio: "שיווק ותיווך",
  guarantees_ratio: "ערבויות וביטוח",
  finance_ratio: "מימון",
  betterment_levy_ratio: "היטל השבחה",
  vat_rate: "מע״מ",
};

export const ASSUMPTION_STATUS: Record<string, { label: string; colour: string }> = {
  data: { label: "נתון", colour: "#1f5f55" },
  estimate: { label: "אומדן", colour: "#8a6100" },
  missing: { label: "חסר", colour: "#a8321e" },
};

export const label = (map: Record<string, string>, id: string) => map[id] ?? id;
