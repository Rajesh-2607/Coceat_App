import { describe, expect, it } from "vitest";
import en from "../i18n/en.json";
import ta from "../i18n/ta.json";
import { MODULE_ORDER, visibleModules } from "./modules";

describe("visibleModules", () => {
  it("shows only enabled modules, in a stable order", () => {
    expect(visibleModules(["money", "sell", "unknown"])).toEqual(["sell", "money"]);
  });
});

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v as object, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("i18n", () => {
  it("Tamil and English have exactly the same keys", () => {
    expect(keys(ta).sort()).toEqual(keys(en).sort());
  });
  it("every module has a nav label", () => {
    for (const m of MODULE_ORDER) expect(en.nav).toHaveProperty(m);
  });
});
