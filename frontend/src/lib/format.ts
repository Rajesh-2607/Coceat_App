/** Edge conversions: the API speaks integer paise and integer base units (grams / pieces). */

const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

/** 150050 -> "₹1,500.50" */
export function formatMoney(paise: number): string {
  const sign = paise < 0 ? "-" : "";
  return `${sign}₹${inr.format(Math.abs(paise) / 100)}`;
}

/** "1,500.5" | "1500" -> 150050. Returns null for empty or invalid input (never NaN). */
export function parseRupees(input: string): number | null {
  const s = input.replaceAll(",", "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null;
  const [whole, frac = ""] = s.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}

/** Paise as an editable rupee string: 150050 -> "1500.5", 150000 -> "1500". */
export function paiseToInput(paise: number): string {
  return String(paise / 100);
}

export type QuantityKind = "weight" | "count";

/** 12500 (grams) -> "12.5 kg"; 40 (pieces) -> "40". */
export function formatQuantity(base: number, kind: QuantityKind, labels: { kg: string; g: string; pcs: string }): string {
  if (kind === "count") return `${inr.format(base)} ${labels.pcs}`;
  if (Math.abs(base) >= 1000) return `${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 }).format(base / 1000)} ${labels.kg}`;
  return `${inr.format(base)} ${labels.g}`;
}

/** Kilograms typed by the user ("12.5") -> grams (12500). Null for empty or invalid input. */
export function parseKg(input: string): number | null {
  const s = input.trim();
  if (!/^\d+(\.\d{1,3})?$/.test(s)) return null;
  const [whole, frac = ""] = s.split(".");
  return Number(whole) * 1000 + Number(frac.padEnd(3, "0"));
}

/** Whole pieces typed by the user. Null for empty or invalid input. */
export function parsePieces(input: string): number | null {
  const s = input.trim();
  return /^\d+$/.test(s) ? Number(s) : null;
}

/** Parse a quantity field for a product kind into base units (grams / pieces). */
export function parseQuantity(input: string, kind: QuantityKind): number | null {
  return kind === "weight" ? parseKg(input) : parsePieces(input);
}

export function formatDateTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale === "ta" ? "ta-IN" : "en-IN", { dateStyle: "medium", timeStyle: "short" });
}
