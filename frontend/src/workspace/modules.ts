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

export function visibleModules(enabled: readonly string[]): ModuleKey[] {
  return MODULE_ORDER.filter((m) => enabled.includes(m));
}
