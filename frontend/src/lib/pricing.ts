/**
 * The bill total shown while making a bill. It mirrors backend/app/modules/sales/pricing.py rule for rule, so the
 * number on screen is the number the server will bill (the server stays the source of truth: the bill it returns is
 * what gets printed). Integer paise only; half-up rounding; tax per line; total rounded to the whole rupee.
 */

export const GST_RATES_BP = [0, 25, 300, 500, 1200, 1800, 2800] as const;

export function lineAmount(quantityBase: number, baseFactor: number, unitPricePaise: number): number {
  return Math.floor((unitPricePaise * quantityBase + Math.floor(baseFactor / 2)) / baseFactor);
}

export function lineTax(taxable: number, rateBp: number, interState: boolean): { cgst: number; sgst: number; igst: number } {
  if (rateBp === 0) return { cgst: 0, sgst: 0, igst: 0 };
  if (interState) return { cgst: 0, sgst: 0, igst: Math.floor((taxable * rateBp + 5_000) / 10_000) };
  const half = Math.floor((taxable * rateBp + 10_000) / 20_000);
  return { cgst: half, sgst: half, igst: 0 };
}

export function roundToRupee(paise: number): number {
  return Math.floor((paise + 50) / 100) * 100;
}

export type PricedLine = { quantityBase: number; baseFactor: number; unitPricePaise: number; gstRateBp: number };

export type Totals = {
  taxable: number;
  cgst: number;
  sgst: number;
  igst: number;
  roundOff: number;
  total: number;
};

export function billTotals(lines: PricedLine[], interState: boolean): Totals {
  let taxable = 0;
  let cgst = 0;
  let sgst = 0;
  let igst = 0;
  for (const l of lines) {
    const t = lineAmount(l.quantityBase, l.baseFactor, l.unitPricePaise);
    const tax = lineTax(t, l.gstRateBp, interState);
    taxable += t;
    cgst += tax.cgst;
    sgst += tax.sgst;
    igst += tax.igst;
  }
  const exact = taxable + cgst + sgst + igst;
  const total = roundToRupee(exact);
  return { taxable, cgst, sgst, igst, roundOff: total - exact, total };
}

/** GST state code = the first two digits of a GSTIN. */
export function gstState(gstin: string | null | undefined): string | null {
  return gstin ? gstin.slice(0, 2) : null;
}
