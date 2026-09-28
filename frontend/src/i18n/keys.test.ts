import { describe, expect, it } from "vitest";
import en from "./en.json";

// every app source file as text (Vite resolves the glob at build time, so no Node APIs are needed)
const sources = import.meta.glob<string>("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true });
const appFiles = Object.entries(sources).filter(([path]) => !/\.test\.tsx?$|\.d\.ts$/.test(path));

function lookup(obj: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>((o, part) => (typeof o === "object" && o !== null ? (o as Record<string, unknown>)[part] : undefined), obj);
}

describe("translation keys used in code", () => {
  it("every static t('...') key exists in en.json", () => {
    const missing: string[] = [];
    for (const [file, text] of appFiles) {
      for (const m of text.matchAll(/\bt\(\s*["'`]([^"'`$]+)["'`]/g)) {
        if (typeof lookup(en, m[1]!) !== "string") missing.push(`${file}: ${m[1]}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("every value in a dynamic key family exists (t(`family.${value}`))", () => {
    const families: Record<string, string[]> = {
      roles: ["owner", "manager", "billing", "stock", "viewer"],
      "locations.kinds": ["shop", "godown", "cold_storage", "other"],
      "catalog.kinds": ["weight", "count"],
      "stock.types": ["opening", "adjustment", "transfer_out", "transfer_in", "wastage", "reversal", "purchase", "sale", "sale_return"],
      "wastage.reasons": ["rotten", "damaged", "shrinkage", "spoiled_in_transit", "other"],
      "crates.entryTypes": ["issued", "returned", "adjustment", "reversal"],
      "parties.entryTypes": ["opening", "sale", "sale_return", "purchase", "purchase_return", "payment_in", "payment_out", "adjustment", "reversal"],
      "parties.tabs": ["ledger", "crates"],
      "staff.roleHint": ["owner", "manager", "billing", "stock", "viewer"],
      "admin.status": ["active", "suspended"],
      "audit.areas": ["location", "product", "unit", "grade", "variety", "customer", "supplier", "party_ledger", "crate_ledger", "stock", "staff", "business", "auth"],
      nav: ["customers", "suppliers", "sell", "stock", "money", "buy", "bills", "wastage", "reports", "staff", "audit", "settings"],
    };
    const missing = Object.entries(families).flatMap(([family, values]) =>
      values.filter((v) => typeof lookup(en, `${family}.${v}`) !== "string").map((v) => `${family}.${v}`),
    );
    expect(missing).toEqual([]);
  });

  it("every backend error code the UI can meet has a message", () => {
    const codes = [
      "insufficient_stock", "unit_kind_mismatch", "unknown_unit", "unit_code_taken", "grade_name_taken", "product_name_taken",
      "variety_name_taken", "variety_mismatch", "product_inactive", "party_phone_taken", "zero_adjustment", "same_location",
      "already_reversed", "not_reversible", "cannot_edit_self", "last_owner", "permission_denied", "module_disabled", "invalid_phone",
    ];
    expect(codes.filter((c) => typeof lookup(en, `errors.${c}`) !== "string")).toEqual([]);
  });
});
