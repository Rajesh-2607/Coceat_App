/** Typed quantity in a chosen unit -> whole base units (grams / pieces), exactly, without floats. */

/**
 * "12.5" with a unit of 1000 (kg) -> 12500. "1.5" with 12 (dozen) -> 18. Returns null for empty or invalid input,
 * or when the amount is not a whole number of base units (e.g. "0.0005" kg would be half a gram).
 */
export function parseQtyToBase(input: string, baseFactor: number): number | null {
  const s = input.trim();
  if (!/^\d+(\.\d{1,6})?$/.test(s)) return null;
  const [whole, frac = ""] = s.split(".");
  const scale = 10 ** frac.length;
  const fracNum = frac === "" ? 0 : Number(frac);
  const scaled = fracNum * baseFactor;
  if (scaled % scale !== 0) return null;
  const base = Number(whole) * baseFactor + scaled / scale;
  return Number.isSafeInteger(base) && base > 0 ? base : null;
}

/** Base units as a number in the given unit for editing: 12500 with 1000 -> "12.5". */
export function baseToUnitText(base: number, baseFactor: number): string {
  const value = base / baseFactor;
  return String(Math.round(value * 1000) / 1000);
}
