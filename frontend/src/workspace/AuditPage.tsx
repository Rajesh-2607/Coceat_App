import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuditEvents, useStaff, type AuditFilters } from "../api/hooks";
import { formatDateTime } from "../lib/format";
import { Card, EmptyState, Field, Input, PageHeader, QueryBoundary, Select } from "../lib/ui";

/** Areas of the app, matched by the first part of an audit action ("stock" matches "stock.transfer"). */
const AREAS = ["location", "product", "unit", "grade", "variety", "customer", "supplier", "party_ledger", "crate_ledger", "stock", "staff", "business", "auth"];

export function AuditPage() {
  const { t, i18n } = useTranslation();
  const staff = useStaff();
  const [area, setArea] = useState("");
  const [actor, setActor] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const filters: AuditFilters = {
    action: area || undefined,
    actor_user_id: actor || undefined,
    // a date picked as "to" includes that whole day
    date_from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
    date_to: to ? new Date(new Date(`${to}T00:00:00`).getTime() + 86_400_000).toISOString() : undefined,
  };
  const events = useAuditEvents(filters);

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.audit")} subtitle={t("audit.subtitle")} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("audit.area")}>
          <Select value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">{t("audit.allAreas")}</option>
            {AREAS.map((a) => (
              <option key={a} value={a}>
                {t(`audit.areas.${a}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("audit.who")}>
          <Select value={actor} onChange={(e) => setActor(e.target.value)}>
            <option value="">{t("audit.everyone")}</option>
            {(staff.data ?? []).map((s) => (
              <option key={s.user_id} value={s.user_id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("audit.from")}>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </Field>
        <Field label={t("audit.to")}>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
      </div>
      <QueryBoundary query={events}>
        {(page) =>
          page.items.length === 0 ? (
            <EmptyState>{t("audit.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {page.items.map((e) => (
                <li key={e.seq}>
                  <Card className="space-y-0.5">
                    <p className="text-lg font-semibold">{t(`audit.actions.${e.action}`, { defaultValue: e.action })}</p>
                    <p className="text-slate-600">
                      {e.actor_name ?? t("audit.system")} · {formatDateTime(e.created_at, i18n.language)}
                    </p>
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
    </section>
  );
}
