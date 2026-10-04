/** Workspace sections, keyed by the backend's module keys. Which ones show is per-business configuration. */
export const MODULE_ORDER = [
  "sell",
  "stock",
  "money",
  "buy",
  "bills",
  "customers",
  "suppliers",
  "wastage",
  "reports",
  "staff",
  "audit",
  "settings",
] as const;

export type ModuleKey = (typeof MODULE_ORDER)[number];

/** Modules whose screens exist. A module not listed here would show a "coming soon" page. */
export const BUILT_MODULES: ReadonlySet<ModuleKey> = new Set(MODULE_ORDER);

/** The permission a member needs to see a module in the menu (the API enforces it regardless). */
const MODULE_PERMISSION: Partial<Record<ModuleKey, string>> = {
  staff: "staff.view",
  audit: "audit.view",
  customers: "parties.view",
  suppliers: "parties.view",
  stock: "stock.view",
  wastage: "stock.view",
  sell: "bills.create",
  bills: "bills.view",
  money: "money.view",
  buy: "purchases.view",
  reports: "reports.view",
};

/** With `permissions`, also hides modules the member's role can't open. */
export function visibleModules(enabled: readonly string[], permissions?: readonly string[]): ModuleKey[] {
  return MODULE_ORDER.filter((m) => {
    if (!enabled.includes(m)) return false;
    const needed = MODULE_PERMISSION[m];
    return permissions === undefined || needed === undefined || permissions.includes(needed);
  });
}
