import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { useMovements, useProducts, useStockBalances, useTransfers } from "../../api/hooks";
import { formatDateTime, formatQuantity } from "../../lib/format";
import { Badge, Card, EmptyState, LinkButton, PageHeader, QueryBoundary, SecondaryButton, TabBar, Button } from "../../lib/ui";
import { useName, useQuantityLabels } from "../../lib/useName";
import { useCurrentLocation } from "../location";
import { CratesTab } from "./CratesTab";
import { ProductsTab } from "./ProductsTab";
import { SetupTab } from "./SetupTab";
import { AdjustSheet, OpeningSheet, ReverseSheet, TransferSheet } from "./StockForms";

type Context = Schemas["WorkspaceContextOut"];

export function StockPage({ context }: { context: Context }) {
  const { t } = useTranslation();
  const can = (perm: string) => context.permissions.includes(perm);
  const tabs = [
    { to: "/w/stock", label: t("stock.tabs.balances"), end: true },
    { to: "/w/stock/movements", label: t("stock.tabs.movements") },
    { to: "/w/stock/transfers", label: t("stock.tabs.transfers") },
    ...(can("catalog.view") ? [{ to: "/w/stock/products", label: t("stock.tabs.products") }] : []),
    ...(can("crates.view") ? [{ to: "/w/stock/crates", label: t("stock.tabs.crates") }] : []),
    { to: "/w/stock/setup", label: t("stock.tabs.setup") },
  ];
  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.stock")} />
      <TabBar tabs={tabs} />
      <Routes>
        <Route index element={<BalancesTab canMove={can("stock.move")} />} />
        <Route path="opening" element={<Navigate to="/w/stock?new=opening" replace />} />
        <Route path="movements" element={<MovementsTab canMove={can("stock.move")} />} />
        <Route path="transfers" element={<TransfersTab canMove={can("stock.move")} />} />
        <Route path="products" element={<ProductsTab canManage={can("catalog.manage")} />} />
        <Route path="crates" element={<CratesTab canManage={can("crates.manage")} />} />
        <Route path="setup" element={<SetupTab canManageLocations={can("locations.manage")} canManageCatalog={can("catalog.manage")} />} />
        <Route path="*" element={<Navigate to="/w/stock" replace />} />
      </Routes>
    </section>
  );
}

/** "Banana · Robusta · A" */
function itemLabel(parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join(" · ");
}

/* ---- balances --------------------------------------------------------------------------------------- */

function BalancesTab({ canMove }: { canMove: boolean }) {
  const { t, i18n } = useTranslation();
  const name = useName();
  const labels = useQuantityLabels();
  const { locationId, locations } = useCurrentLocation();
  const balances = useStockBalances(locationId);
  const [params, setParams] = useSearchParams();
  const [sheet, setSheet] = useState<"opening" | "adjust" | null>(params.get("new") === "opening" ? "opening" : null);
  const close = () => {
    setSheet(null);
    if (params.has("new")) setParams({}, { replace: true });
  };
  const locationName = (id: string) => {
    const l = locations.find((x) => x.id === id);
    return l ? name(l) : "";
  };

  return (
    <div className="space-y-4">
      {canMove && (
        <div className="grid grid-cols-2 gap-2">
          <Button onClick={() => setSheet("opening")}>📥 {t("stock.receive")}</Button>
          <SecondaryButton onClick={() => setSheet("adjust")}>✏️ {t("stock.adjust")}</SecondaryButton>
        </div>
      )}
      <QueryBoundary query={balances}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("stock.emptyBalances")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((r) => {
                const productName = i18n.language === "ta" && r.product_name_ta ? r.product_name_ta : r.product_name;
                const variety = i18n.language === "ta" && r.variety_name_ta ? r.variety_name_ta : r.variety_name;
                const grade = i18n.language === "ta" && r.grade_name_ta ? r.grade_name_ta : r.grade_name;
                return (
                  <li key={`${r.location_id}|${r.product_id}|${r.variety_id}|${r.grade_id}`}>
                    <Card className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-lg font-semibold">{itemLabel([productName, variety, grade])}</p>
                        {locationId === null && <p className="text-sm text-slate-500">{locationName(r.location_id)}</p>}
                      </div>
                      <p className={`shrink-0 text-xl font-bold ${r.quantity < 0 ? "text-rose-600" : ""}`}>
                        {formatQuantity(r.quantity, r.kind, labels)}
                      </p>
                    </Card>
                  </li>
                );
              })}
            </ul>
          )
        }
      </QueryBoundary>
      {sheet === "opening" && <OpeningSheet onClose={close} />}
      {sheet === "adjust" && <AdjustSheet onClose={close} />}
    </div>
  );
}

/* ---- movements -------------------------------------------------------------------------------------- */

const REVERSIBLE = new Set(["opening", "adjustment", "wastage"]);

function MovementsTab({ canMove }: { canMove: boolean }) {
  const { t, i18n } = useTranslation();
  const name = useName();
  const labels = useQuantityLabels();
  const { locationId, locations } = useCurrentLocation();
  const movements = useMovements(locationId);
  const products = useProducts(true);
  const [reversing, setReversing] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <QueryBoundary query={movements}>
        {(rows) => {
          const reversed = new Set(rows.map((m) => m.reversal_of).filter(Boolean));
          if (rows.length === 0) return <EmptyState>{t("stock.emptyMovements")}</EmptyState>;
          return (
            <ul className="space-y-2">
              {rows.map((m) => {
                const product = products.data?.find((p) => p.id === m.product_id);
                const variety = product?.varieties.find((v) => v.id === m.variety_id);
                const location = locations.find((l) => l.id === m.location_id);
                const canReverse = canMove && REVERSIBLE.has(m.movement_type) && !reversed.has(m.id);
                return (
                  <li key={m.id}>
                    <Card className="space-y-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-lg font-semibold">
                          {itemLabel([product ? name(product) : "…", variety ? name(variety) : null])}
                        </p>
                        <p className={`shrink-0 text-lg font-bold ${m.quantity < 0 ? "text-rose-600" : "text-emerald-600"}`}>
                          {m.quantity > 0 ? "+" : "−"}
                          {formatQuantity(Math.abs(m.quantity), product?.kind ?? "count", labels)}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
                        <Badge tone={m.quantity < 0 ? "bad" : "good"}>{t(`stock.types.${m.movement_type}`)}</Badge>
                        {location && <span>{name(location)}</span>}
                        <span>{formatDateTime(m.created_at, i18n.language)}</span>
                        {reversed.has(m.id) && <Badge tone="warn">{t("stock.reversed")}</Badge>}
                      </div>
                      {m.reason && <p className="text-slate-600">{m.reason}</p>}
                      {canReverse && <LinkButton onClick={() => setReversing(m.id)}>{t("stock.reverse")}</LinkButton>}
                    </Card>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </QueryBoundary>
      {reversing && <ReverseSheet movementId={reversing} onClose={() => setReversing(null)} />}
    </div>
  );
}

/* ---- transfers -------------------------------------------------------------------------------------- */

function TransfersTab({ canMove }: { canMove: boolean }) {
  const { t, i18n } = useTranslation();
  const name = useName();
  const labels = useQuantityLabels();
  const { locations } = useCurrentLocation();
  const transfers = useTransfers();
  const products = useProducts(true);
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(params.get("new") === "1");
  const close = () => {
    setOpen(false);
    if (params.has("new")) setParams({}, { replace: true });
  };
  const locationName = (id: string) => {
    const l = locations.find((x) => x.id === id);
    return l ? name(l) : "…";
  };

  return (
    <div className="space-y-3">
      {canMove && <Button onClick={() => setOpen(true)}>🔀 {t("stock.newTransfer")}</Button>}
      <QueryBoundary query={transfers}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("stock.emptyTransfers")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((tr) => (
                <li key={tr.id}>
                  <Card className="space-y-1">
                    <p className="text-lg font-semibold">
                      {locationName(tr.from_location_id)} → {locationName(tr.to_location_id)}
                    </p>
                    <p className="text-sm text-slate-500">{formatDateTime(tr.created_at, i18n.language)}</p>
                    <ul className="text-slate-700">
                      {tr.movements
                        .filter((m) => m.movement_type === "transfer_out")
                        .map((m) => {
                          const p = products.data?.find((x) => x.id === m.product_id);
                          return (
                            <li key={m.id}>
                              {p ? name(p) : "…"} — {formatQuantity(Math.abs(m.quantity), p?.kind ?? "count", labels)}
                            </li>
                          );
                        })}
                    </ul>
                    {tr.note && <p className="text-slate-600">{tr.note}</p>}
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {open && <TransferSheet onClose={close} />}
    </div>
  );
}
