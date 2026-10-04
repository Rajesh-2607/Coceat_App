import { describe, expect, it } from "vitest";
import { billTotals, gstState, lineAmount, lineTax, roundToRupee } from "./pricing";

// The same vectors as backend/tests/test_pricing.py: the screen and the server must agree to the paisa.
describe("pricing (mirror of the backend)", () => {
  it("rounds each line half-up", () => {
    expect(lineAmount(12_500, 1_000, 4_500)).toBe(56_250);
    expect(lineAmount(1, 1_000, 4_500)).toBe(5);
    expect(lineAmount(1, 1_000, 4_400)).toBe(4);
    expect(lineAmount(3, 3, 999)).toBe(999);
    expect(lineAmount(0, 1_000, 5_000)).toBe(0);
  });

  it("splits GST equally within the state and charges IGST across states", () => {
    expect(lineTax(10_000, 500, false)).toEqual({ cgst: 250, sgst: 250, igst: 0 });
    expect(lineTax(1_001, 500, false)).toEqual({ cgst: 25, sgst: 25, igst: 0 });
    expect(lineTax(10_000, 0, false)).toEqual({ cgst: 0, sgst: 0, igst: 0 });
    expect(lineTax(10_000, 1_800, true)).toEqual({ cgst: 0, sgst: 0, igst: 1_800 });
    expect(lineTax(333, 500, true)).toEqual({ cgst: 0, sgst: 0, igst: 17 });
  });

  it("rounds the bill to the whole rupee", () => {
    for (const [paise, rupee] of [[0, 0], [49, 0], [50, 100], [99, 100], [149, 100], [150, 200], [1_234_567, 1_234_600]]) {
      expect(roundToRupee(paise!)).toBe(rupee);
    }
  });

  it("shows the round-off and keeps the totals balanced", () => {
    const t = billTotals([{ quantityBase: 12_500, baseFactor: 1_000, unitPricePaise: 4_500, gstRateBp: 0 }], false);
    expect(t).toEqual({ taxable: 56_250, cgst: 0, sgst: 0, igst: 0, roundOff: 50, total: 56_300 });
    const gst = billTotals([{ quantityBase: 2_000, baseFactor: 1_000, unitPricePaise: 10_000, gstRateBp: 500 }], false);
    expect(gst).toEqual({ taxable: 20_000, cgst: 500, sgst: 500, igst: 0, roundOff: 0, total: 21_000 });
    expect(billTotals([{ quantityBase: 2_000, baseFactor: 1_000, unitPricePaise: 10_000, gstRateBp: 500 }], true).igst).toBe(1_000);
  });

  it("reads the state from a GSTIN", () => {
    expect(gstState("33ABCDE1234F1Z5")).toBe("33");
    expect(gstState(null)).toBeNull();
    expect(gstState("")).toBeNull();
  });
});
