/** ‏W1–W2 · השדות שהתיק מקבל מהשרת על השטח לפי המדיניות ועל הכלכלה שמחושבת עליו.
 *
 *  בקובץ נפרד מ-`api.ts` כדי שעבודה על מסך הסריקה ועל התיק לא תיגע באותו קובץ. */
import type { Dossier } from "@/lib/api";

export interface PolicyAreaCase {
  sqm: number;
  far_pct: number | null;
  share_of_cap: number | null;
  gap_sqm: number | null;
  gap_far_pct: number | null;
  unrealizable_share: number | null;
}

/** השטח שנכנס בתוך קווי הבניין והנסיגות. ‏`why` כשלא ניתן לחשב. */
export interface PolicyArea {
  why?: string;
  plot_sqm?: number;
  envelope_sqm?: number;
  envelope_share_of_plot?: number | null;
  cap_400_sqm?: number | null;
  cap_400_far_pct?: number | null;
  floors?: { low: number; high: number };
  corner?: boolean | null;
  binding?: "envelope" | "cap";
  certainty?: string;
  eta?: number;
  limits?: string[];
  assumptions?: string[];
  sources?: { label: string; url: string }[];
  low?: PolicyAreaCase;
  base?: PolicyAreaCase;
  high?: PolicyAreaCase;
}

export interface ScenarioCard {
  area_sqm: number;
  far_pct: number | null;
  developer_allocation_sqm: number;
  total_revenue_ils: number;
  total_cost_before_levy_ils: number;
  profit_before_levy_ils: number;
  margin_before_levy: number;
  levy_ceiling_ils: number | null;
  levy_estimate_ils: number | null;
  profit_after_levy_ils: number | null;
  margin_after_levy: number | null;
  meets_target: boolean;
}

export interface AfterLevy {
  betterment_ils: number;
  levy_ils: number;
  levy_low_ils: number;
  levy_high_ils: number;
  profit_ils: number;
  margin: number;
  margin_low: number;
  margin_high: number;
  meets_target: boolean;
  /** ‏W8 · ההשבחה הוזנה על ידי היזם — מספר אחד, בלי טווח. */
  manual?: boolean;
}

/** ‏A כלכלי לפי המדיניות · B רק עם הגדלת זכויות · C לא גם ב-400% · D לא חושב. */
export interface RightsVerdict {
  case: "A" | "B" | "C" | "D";
  basis: "after_levy" | "before_levy" | null;
  text: string;
  required_area_sqm?: number;
  required_addition_sqm?: number;
  required_share_of_cap?: number | null;
  required_far_pct?: number | null;
  addition_far_pct?: number | null;
}

export type PolicyDossier = Dossier & {
  rights: Dossier["rights"] & { policy_area?: PolicyArea };
  economics: Dossier["economics"] & {
    after_levy?: AfterLevy | null;
    before_levy?: { profit_ils: number; margin: number; meets_target: boolean };
    area_basis?: "policy" | "cap_400";
    buildable_area_sqm?: number;
    scenarios?: { policy: ScenarioCard | null; cap_400: ScenarioCard };
    rights_verdict?: RightsVerdict;
    cost_rows?: CostRow[];
  };
};

/** ‏W3 · פסקה אחת בהסבר ההיטל: מה ההיטל, האומדן, הטווח, התקרה, הקטגוריה. */
export interface LevyExplainParagraph { id: string; title: string; text: string }

/** ‏W4 · שורה בטבלת העלויות: מה היא, הנוסחה עם המספרים, ומאיפה הקלט. */
export interface CostRow { id: string; label: string; value_ils: number; formula: string; explain: string; source: string }

// ── W8 · מחשבון התרחיש ──

/** השטח שהתרחיש מחושב עליו. ‏`policy` בתשובה הוא אומדן הבסיס לפי המדיניות. */
export type AreaBasis = "policy_low" | "policy_base" | "policy_high" | "cap_400" | "custom";

export interface MixRow { rooms: 3 | 4 | 5; units: number }

/** מה שהיזם שינה. שדה שלא נשלח נשאר ברירת המחדל של התיק. */
export interface ScenarioOverrides {
  area_basis?: AreaBasis;
  custom_area_sqm?: number;
  sale_price_per_sqm?: number;
  construction_cost_per_sqm?: number;
  underground_cost_per_sqm?: number;
  tenant_compensation_sqm_per_existing_unit?: number;
  average_existing_unit_sqm?: number;
  existing_price_per_sqm?: number;
  betterment_ils?: number;
  developer_profit_target_ratio?: number;
  finance_ratio?: number;
  mix?: "optimize" | MixRow[];
}

/** ערך אחד שהיזם שינה, מול ברירת המחדל — אותה רשימה ב-PDF ובאקסל. */
export interface OverrideApplied {
  id: string;
  label: string;
  default: number | string | null;
  value: number | string;
  unit: string;
  unit_label: string;
}

/** התמהיל של התרחיש. בלי תמהיל: ‏`{rows: [], summary: null}`. */
export interface ScenarioMix {
  rows: { rooms: number; area_sqm: number; units: number }[];
  summary: string | null;
  source?: "optimize" | "developer";
  developer_units?: number;
  tenant_units?: number;
  developer_used_sqm?: number;
  developer_available_sqm?: number;
  unused_developer_sqm?: number;
  developer_sale_revenue_ils?: number;
  policy_warnings?: string[];
  notes?: string[];
}

export interface LiveInput { value: number | null; resolved: boolean; label: string; certainty?: string }

export type ScenarioEconomics = Omit<PolicyDossier["economics"], "area_basis" | "unit_mix"> & {
  area_basis?: "policy" | "policy_low" | "policy_high" | "cap_400" | "custom";
  live_inputs?: { sale_price?: LiveInput; unit_area?: LiveInput; existing_price?: LiveInput };
  unit_mix?: ScenarioMix;
  overrides_applied?: OverrideApplied[];
};

export interface ScenarioResponse {
  economics: ScenarioEconomics;
  overrides_applied: OverrideApplied[];
}
