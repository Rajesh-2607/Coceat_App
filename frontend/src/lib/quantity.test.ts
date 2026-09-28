import { describe, expect, it } from "vitest";
import { addDays } from "./dates";
import { baseToUnitText, parseQtyToBase } from "./quantity";

describe("parseQtyToBase", () => {
  it("converts kilograms and dozens exactly", () => {
    expect(parseQtyToBase("12.5", 1000)).toBe(12_500);
    expect(parseQtyToBase("0.001", 1000)).toBe(1);
    expect(parseQtyToBase("3", 1)).toBe(3);
    expect(parseQtyToBase("1.5", 12)).toBe(18);
    expect(parseQtyToBase("100", 100_000)).toBe(10_000_000);
  });

  it("refuses partial base units and bad input", () => {
    expect(parseQtyToBase("0.0005", 1000)).toBeNull();
    expect(parseQtyToBase("1.5", 1)).toBeNull(); // half a piece
    for (const bad of ["", "abc", "-1", "0", "1e3", "1.", ".5"]) expect(parseQtyToBase(bad, 1000)).toBeNull();
  });

  it("turns base units back into editable text", () => {
    expect(baseToUnitText(12_500, 1000)).toBe("12.5");
    expect(baseToUnitText(18, 12)).toBe("1.5");
    expect(baseToUnitText(1, 3)).toBe("0.333");
  });
});

describe("addDays", () => {
  it("moves across month and year ends", () => {
    expect(addDays("2026-09-28", 3)).toBe("2026-10-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
  });
});
