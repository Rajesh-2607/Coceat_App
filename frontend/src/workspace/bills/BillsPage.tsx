import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useBills, type BillFilters } from "../../api/hooks";
import { formatDateTime, formatMoney } from "../../lib/format";
import { Badge, Card, EmptyState, Input, PageHeader, QueryBoundary, Select } from "../../lib/ui";

export function BillsPage() {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "active" | "void">("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const filters: BillFilters = {
    q: q.trim() || undefined,
    status: status || undefined,
    date_from: from || undefined,
    date_to: to || undefined,
  };
  const bills = useBills(filters);

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.bills")} />
      <Input type="search" placeholder={t("bills.search")} aria-label={t("bills.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="grid grid-cols-3 gap-2">
        <Select aria-label={t("bills.status")} value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
          <option value="">{t("bills.allStatuses")}</option>
          <option value="active">{t("bills.statuses.active")}</option>
          <option value="void">{t("bills.statuses.void")}</option>
        </Select>
        <Input type="date" aria-label={t("audit.from")} value={from} onChange={(e) => setFrom(e.target.value)} />
        <Input type="date" aria-label={t("audit.to")} value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <QueryBoundary query={bills}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("bills.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((b) => (
                <li key={b.id}>
                  <Link to={`/w/bills/${b.id}`} className="block">
                    <Card className="flex items-center justify-between gap-3 active:bg-violet-50">
                      <div className="min-w-0">
                        <p className="truncate text-lg font-semibold">{b.bill_number}</p>
                        <p className="truncate text-sm text-slate-500">
                          {b.party_name ?? t("sell.walkIn")} · {formatDateTime(b.created_at, i18n.language)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className={`text-lg font-bold ${b.status === "void" ? "text-slate-400 line-through" : ""}`}>
                          {formatMoney(b.total_paise)}
                        </p>
                        {b.status === "void" ? (
                          <Badge tone="bad">{t("bills.statuses.void")}</Badge>
                        ) : b.paid_paise < b.total_paise ? (
                          <Badge tone="warn">{t("bills.credit", { amount: formatMoney(b.total_paise - b.paid_paise) })}</Badge>
                        ) : (
                          <Badge tone="good">{t("bills.paid")}</Badge>
                        )}
                      </div>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
    </section>
  );
}
