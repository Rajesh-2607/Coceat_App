import { describe, expect, it } from "vitest";
import { formatMoney, formatQuantity, paiseToInput, parseKg, parsePieces, parseQuantity, parseRupees } from "./format";

const labels = { kg: "kg", g: "g", pcs: "pcs" };

describe("money", () => {
  it("formats paise in Indian grouping", () => {
    expect(formatMoney(150050)).toBe("₹1,500.5");
    expect(formatMoney(1234567800)).toBe("₹1,23,45,678");
    expect(formatMoney(-9900)).toBe("-₹99");
    expect(formatMoney(0)).toBe("₹0");
  });

  it("parses rupee input exactly, without float error", () => {
    expect(parseRupees("1500")).toBe(150000);
    expect(parseRupees("1,500.5")).toBe(150050);
    expect(parseRupees("0.29")).toBe(29);
    expect(parseRupees("19.99")).toBe(1999);
  });

  it("rejects invalid rupee input", () => {
    for (const bad of ["", "abc", "1.234", "-5", "1e3", "1.", ".5"]) expect(parseRupees(bad)).toBeNull();
  });

  it("round-trips paise through the editable string", () => {
    expect(parseRupees(paiseToInput(150050))).toBe(150050);
    expect(paiseToInput(150000)).toBe("1500");
  });
});

describe("quantity", () => {
  it("shows kilograms above 1000 g, grams below, pieces for counts", () => {
    expect(formatQuantity(12500, "weight", labels)).toBe("12.5 kg");
    expect(formatQuantity(750, "weight", labels)).toBe("750 g");
    expect(formatQuantity(40, "count", labels)).toBe("40 pcs");
  });

  it("parses kg into whole grams", () => {
    expect(parseKg("12.5")).toBe(12500);
    expect(parseKg("0.001")).toBe(1);
    expect(parseKg("100")).toBe(100000);
    expect(parseKg("1.2345")).toBeNull();
    expect(parseKg("")).toBeNull();
  });

  it("parses pieces as whole numbers only", () => {
    expect(parsePieces("40")).toBe(40);
    expect(parsePieces("4.5")).toBeNull();
    expect(parseQuantity("2", "weight")).toBe(2000);
    expect(parseQuantity("2", "count")).toBe(2);
  });
});
