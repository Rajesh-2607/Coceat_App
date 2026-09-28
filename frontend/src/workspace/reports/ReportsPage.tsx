import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useGstReport, useOutstandingReport, useProducts, useSalesReport, useWastageReport } from "../../api/hooks";
import { monthStartIst, todayIst } from "../../lib/dates";
import { formatMoney, formatQuantity } from "../../lib/format";
import { Card, EmptyState, Field, Input, PageHeader, QueryBoundary, StatTile } from "../../lib/ui";
import { useName, useQuantityLabels } from "../../lib/useName";

type Tab = "sales" | "gst" | "outstanding" | "wastage";
const TABS: Tab[] = ["sales", "gst", "outstanding", "wastage"];

export function ReportsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("sales");
  const [from, setFrom] = useState(monthStartIst());
  const [to, setTo] = useState(todayIst());
  const ranged = tab !== "outstanding";
  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.reports")} />
      <div className="flex gap-2 overflow-x-auto pb-1">
        {TABS.map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`min-h-11 shrink-0 rounded-full px-4 text-base font-medium ${tab === k ? "bg-violet-700 text-white" : "bg-white ring-1 ring-slate-200"}`}
          >
            {t(`reports.tabs.${k}`)}
          </button>
        ))}
      </div>
      {ranged && (
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("audit.from")}>
            <Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label={t("audit.to")}>
            <Input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      )}
      {tab === "sales" && <SalesTab from={from} to={to} />}
      {tab === "gst" && <GstTab from={from} to={to} />}
      {tab === "outstanding" && <OutstandingTab />}
      {tab === "wastage" && <WastageTab from={from} to={to} />}
    </section>
  );
}

function SalesTab({ from, to }: { from: string; to: string }) {
  const { t } = useTranslation();
  const labels = useQuantityLabels();
  const report = useSalesReport(from, to);
  const products = useProducts(true);
  return (
    <QueryBoundary query={report}>
      {(r) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <StatTile label={t("reports.sales")} value={formatMoney(r.totals.total_paise)} tone="good" hint={t("money.bills", { count: r.totals.bills })} />
            <StatTile label={t("reports.tax")} value={formatMoney(r.totals.tax_paise)} />
            <StatTile label={t("reports.collected")} value={formatMoney(r.totals.collected_paise)} tone="brand" />
            <StatTile label={t("reports.returns")} value={formatMoney(r.totals.returns_paise)} tone="warn" hint={t("money.bills", { count: r.totals.returns })} />
          </div>
          <Card className="space-y-2">
            <h2 className="text-lg font-bold">{t("reports.byProduct")}</h2>
            {r.by_product.length === 0 ? (
              <EmptyState>{t("reports.none")}</EmptyState>
            ) : (
              <ul className="divide-y">
                {r.by_product.map((p) => (
                  <li key={p.product_id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{p.description}</p>
                      <p className="text-sm text-slate-500">{formatQuantity(p.quantity_base, products.data?.find((x) => x.id === p.product_id)?.kind ?? "count", labels)}</p>
                    </div>
                    <p className="shrink-0 text-lg font-bold">{formatMoney(p.total_paise)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="space-y-2">
            <h2 className="text-lg font-bold">{t("reports.byDay")}</h2>
            {r.by_day.length === 0 ? (
              <EmptyState>{t("reports.none")}</EmptyState>
            ) : (
              <ul className="divide-y">
                {r.by_day.map((d) => (
                  <li key={d.date} className="flex justify-between py-2">
                    <span>{d.date} · {t("money.bills", { count: d.bills })}</span>
                    <b>{formatMoney(d.total_paise)}</b>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </QueryBoundary>
  );
}

function GstTab({ from, to }: { from: string; to: string }) {
  const { t } = useTranslation();
  const report = useGstReport(from, to);
  return (
    <QueryBoundary query={report}>
      {(r) => (
        <div className="space-y-4">
          <StatTile label={t("reports.totalTax")} value={formatMoney(r.total_tax_paise)} tone="brand" hint={t("reports.gstHint")} />
          <Card className="overflow-x-auto">
            {r.rows.length === 0 ? (
              <EmptyState>{t("reports.none")}</EmptyState>
            ) : (
              <table className="w-full text-right">
                <thead>
                  <tr className="border-b text-sm text-slate-500">
                    <th className="py-2 text-left">{t("reports.rate")}</th>
                    <th>{t("bill.taxable")}</th>
                    <th>CGST</th>
                    <th>SGST</th>
                    <th>IGST</th>
                  </tr>
                </thead>
                <tbody>
                  {r.rows.map((g) => (
                    <tr key={g.gst_rate_bp} className="border-b">
                      <td className="py-2 text-left font-semibold">{g.gst_rate_bp / 100}%</td>
                      <td>{formatMoney(g.taxable_paise)}</td>
                      <td>{formatMoney(g.cgst_paise)}</td>
                      <td>{formatMoney(g.sgst_paise)}</td>
                      <td>{formatMoney(g.igst_paise)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}
    </QueryBoundary>
  );
}

function OutstandingTab() {
  const { t } = useTranslation();
  const name = useName();
  const report = useOutstandingReport();
  return (
    <QueryBoundary query={report}>
      {(r) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <StatTile label={t("home.customerPending")} value={formatMoney(r.owed_to_us_paise)} tone="warn" />
            <StatTile label={t("home.supplierPending")} value={formatMoney(r.we_owe_paise)} tone="bad" />
          </div>
          {(
            [
              ["customers", r.customers],
              ["suppliers", r.suppliers],
            ] as const
          ).map(([kind, list]) => (
            <Card key={kind} className="space-y-2">
              <h2 className="text-lg font-bold">{t(`nav.${kind}`)}</h2>
              {list.length === 0 ? (
                <EmptyState>{t("reports.none")}</EmptyState>
              ) : (
                <ul className="divide-y">
                  {list.map((p) => (
                    <li key={p.party_id}>
                      <Link to={`/w/${kind}/${p.party_id}`} className="flex min-h-12 items-center justify-between gap-3">
                        <span className="truncate font-semibold text-violet-700">{name(p)}</span>
                        <span className={`shrink-0 text-lg font-bold ${p.balance_paise > 0 ? "text-amber-600" : "text-rose-600"}`}>
                          {formatMoney(Math.abs(p.balance_paise))}
                          <span className="ml-1 text-sm font-normal text-slate-500">{p.balance_paise > 0 ? t("parties.theyOwe") : t("parties.youOwe")}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          ))}
        </div>
      )}
    </QueryBoundary>
  );
}

function WastageTab({ from, to }: { from: string; to: string }) {
  const { t } = useTranslation();
  const name = useName();
  const labels = useQuantityLabels();
  const report = useWastageReport(from, to);
  const products = useProducts(true);
  return (
    <QueryBoundary query={report}>
      {(r) =>
        r.rows.length === 0 ? (
          <EmptyState>{t("reports.none")}</EmptyState>
        ) : (
          <ul className="space-y-2">
            {r.rows.map((row) => {
              const p = products.data?.find((x) => x.id === row.product_id);
              return (
                <li key={`${row.reason_code}|${row.product_id}`}>
                  <Card className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-lg font-semibold">{p ? name(p) : "…"}</p>
                      <p className="text-sm text-slate-500">{t(`wastage.reasons.${row.reason_code}`)}</p>
                    </div>
                    <p className="shrink-0 text-lg font-bold text-rose-600">{formatQuantity(row.quantity_base, p?.kind ?? "count", labels)}</p>
                  </Card>
                </li>
              );
            })}
          </ul>
        )
      }
    </QueryBoundary>
  );
}
