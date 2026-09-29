import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "../api/client";
import {
  useAdminCreatePlan,
  useAdminPlans,
  useAdminSubscriptions,
  useAdminSubscriptionStats,
  useAdminUpdatePlan,
  type SubscriptionStatus,
} from "../api/hooks";
import { formatDateTime, formatMoney } from "../lib/format";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, Select, Sheet, StatTile } from "../lib/ui";
import { useName } from "../lib/useName";

type Plan = Schemas["PlanOut"];
type Tab = "subscriptions" | "plans";
const STATUSES: SubscriptionStatus[] = ["trial", "active", "past_due", "cancelled"];

/** Which plan each business is on, and the plan catalog itself. Informational only — no payment gateway. */
export function SubscriptionsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("subscriptions");
  return (
    <section className="space-y-4">
      <PageHeader title={t("admin.subscriptions")} subtitle={t("admin.subscriptionsHint")} />
      <div className="flex gap-2">
        {(["subscriptions", "plans"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`min-h-11 rounded-full px-4 text-base font-medium ${tab === k ? "bg-violet-700 text-white" : "bg-white ring-1 ring-slate-200"}`}
          >
            {t(`admin.subTabs.${k}`)}
          </button>
        ))}
      </div>
      {tab === "subscriptions" ? <SubscriptionsList /> : <PlansCatalog />}
    </section>
  );
}

function SubscriptionsList() {
  const { t, i18n } = useTranslation();
  const [status, setStatus] = useState<SubscriptionStatus | "">("");
  const stats = useAdminSubscriptionStats();
  const subs = useAdminSubscriptions(status || undefined);
  const plans = useAdminPlans();
  const cycleOf = (planKey: string) => plans.data?.find((p) => p.key === planKey)?.billing_period;

  return (
    <div className="space-y-4">
      <QueryBoundary query={stats}>
        {(s) => (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label={t("admin.mrr")} value={formatMoney(s.mrr_paise)} pill={{ label: t("admin.pillLive"), tone: "brand" }} />
            <StatTile label={t("admin.subStatus.active")} value={s.active} pill={{ label: t("admin.pillLive"), tone: "good" }} />
            <StatTile
              label={t("admin.subStatus.trial")}
              value={s.trial}
              hint={t("admin.expiringSoonHint", { count: s.expiring_soon })}
              pill={{ label: t("admin.pillWatch"), tone: "warn" }}
            />
            <StatTile
              label={t("admin.paymentFailures")}
              value={s.payment_failures}
              pill={{ label: t("admin.pillAlert"), tone: s.payment_failures > 0 ? "bad" : "neutral" }}
            />
          </div>
        )}
      </QueryBoundary>

      <Select aria-label={t("admin.filterByStatus")} value={status} onChange={(e) => setStatus(e.target.value as SubscriptionStatus | "")}>
        <option value="">{t("admin.allStatuses")}</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {t(`admin.subStatus.${s}`)}
          </option>
        ))}
      </Select>

      <QueryBoundary query={subs}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("admin.noSubscriptions")}</EmptyState>
          ) : (
            <Card className="space-y-0 overflow-x-auto !p-0">
              <div className="border-b border-slate-100 p-4">
                <h2 className="text-lg font-bold">{t("admin.planLedger")}</h2>
              </div>
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead>
                  <tr className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-2">{t("admin.colBusiness")}</th>
                    <th className="px-4 py-2">{t("admin.plan")}</th>
                    <th className="px-4 py-2">{t("admin.cycle")}</th>
                    <th className="px-4 py-2">{t("admin.colAmount")}</th>
                    <th className="px-4 py-2">{t("admin.renews")}</th>
                    <th className="px-4 py-2">{t("admin.colStatus")}</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => {
                    const renewal = s.status === "trial" ? s.trial_ends_at : s.current_period_end;
                    const cycle = cycleOf(s.plan_key);
                    return (
                      <tr key={s.id} className="border-t border-slate-100">
                        <td className="px-4 py-3 font-semibold">{(i18n.language === "ta" && s.business_name_ta) || s.business_name}</td>
                        <td className="px-4 py-3 text-slate-500">{s.plan_key}</td>
                        <td className="px-4 py-3 text-slate-500">{cycle ? t(`admin.billingPeriod.${cycle}`) : "—"}</td>
                        <td className="px-4 py-3">{s.price_paise != null ? formatMoney(s.price_paise) : t("admin.contactUs")}</td>
                        <td className="px-4 py-3 text-slate-500">{renewal ? formatDateTime(renewal, i18n.language) : "—"}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            <Badge tone={s.status === "active" ? "good" : s.status === "past_due" ? "bad" : s.status === "cancelled" ? "neutral" : "brand"}>
                              {t(`admin.subStatus.${s.status}`)}
                            </Badge>
                            {s.payment_status === "failed" && <Badge tone="bad">{t("admin.paymentFailed")}</Badge>}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link to={`/admin/businesses/${s.business_id}`} className="font-medium text-violet-700">
                            {t("admin.manage")}
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )
        }
      </QueryBoundary>
    </div>
  );
}

function PlansCatalog() {
  const { t } = useTranslation();
  const name = useName();
  const plans = useAdminPlans();
  const [editing, setEditing] = useState<Plan | "new" | null>(null);

  return (
    <div className="space-y-3">
      <Button className="!w-auto" onClick={() => setEditing("new")}>
        + {t("admin.newPlan")}
      </Button>
      <QueryBoundary query={plans}>
        {(rows) => (
          <ul className="space-y-2">
            {rows.map((p) => (
              <li key={p.key}>
                <Card className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className={`truncate text-lg font-semibold ${p.is_active ? "" : "text-slate-400 line-through"}`}>{name(p)}</p>
                    <p className="text-sm text-slate-500">
                      {p.price_paise != null ? `${formatMoney(p.price_paise)} / ${t(`admin.billingPeriod.${p.billing_period}`)}` : t("admin.contactUs")}
                      {p.trial_days ? ` · ${t("admin.trialDaysCount", { count: p.trial_days })}` : ""}
                    </p>
                  </div>
                  <LinkButton onClick={() => setEditing(p)}>{t("common.edit")}</LinkButton>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
      {editing && <PlanSheet plan={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function PlanSheet({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const { t } = useTranslation();
  const create = useAdminCreatePlan();
  const update = useAdminUpdatePlan(plan?.key ?? "");
  const [key, setKey] = useState(plan?.key ?? "");
  const [nameEn, setNameEn] = useState(plan?.name ?? "");
  const [nameTa, setNameTa] = useState(plan?.name_ta ?? "");
  const [period, setPeriod] = useState<Schemas["PlanCreate"]["billing_period"]>(plan?.billing_period ?? "monthly");
  const [price, setPrice] = useState(plan?.price_paise != null ? String(plan.price_paise / 100) : "");
  const [contactUs, setContactUs] = useState(plan ? plan.price_paise == null : false);
  const [trialDays, setTrialDays] = useState(plan?.trial_days != null ? String(plan.trial_days) : "");
  const [active, setActive] = useState(plan?.is_active ?? true);
  const write = plan ? update : create;
  const keyValid = /^[a-z][a-z0-9_]*$/.test(key);
  const priceValue = contactUs ? null : Number(price) * 100;
  const priceInvalid = !contactUs && (price.trim() === "" || Number.isNaN(priceValue));
  const daysValue = trialDays.trim() === "" ? null : Number(trialDays);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (priceInvalid) return;
    if (plan) {
      update.mutate({ name: nameEn, name_ta: nameTa, price_paise: priceValue, is_active: active }, { onSuccess: onClose });
    } else {
      if (!keyValid) return;
      create.mutate(
        { key, name: nameEn, name_ta: nameTa, price_paise: priceValue, billing_period: period, trial_days: period === "trial" ? daysValue : null },
        { onSuccess: onClose },
      );
    }
  }

  return (
    <Sheet title={plan ? t("admin.editPlan") : t("admin.newPlan")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {!plan && (
          <Field label={t("admin.verticalKey")} hint={t("admin.planKeyHint")}>
            <Input required maxLength={40} pattern="[a-z][a-z0-9_]*" value={key} onChange={(e) => setKey(e.target.value.toLowerCase())} aria-invalid={key.length > 0 && !keyValid} autoFocus />
          </Field>
        )}
        <Field label={t("admin.name")}>
          <Input required maxLength={80} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("admin.nameTa")}>
          <Input required maxLength={120} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        {!plan && (
          <Field label={t("admin.billingPeriodLabel")}>
            <Select value={period} onChange={(e) => setPeriod(e.target.value as typeof period)}>
              <option value="trial">{t("admin.billingPeriod.trial")}</option>
              <option value="monthly">{t("admin.billingPeriod.monthly")}</option>
              <option value="yearly">{t("admin.billingPeriod.yearly")}</option>
            </Select>
          </Field>
        )}
        {!plan && period === "trial" && (
          <Field label={t("admin.trialDaysLabel")}>
            <Input required inputMode="numeric" value={trialDays} onChange={(e) => setTrialDays(e.target.value.replace(/\D/g, ""))} />
          </Field>
        )}
        <label className="flex min-h-11 items-center gap-2 text-lg">
          <input type="checkbox" className="size-5" checked={contactUs} onChange={(e) => setContactUs(e.target.checked)} />
          {t("admin.contactUsPricing")}
        </label>
        {!contactUs && (
          <Field label={`${t("admin.price")} (₹)`}>
            <Input required inputMode="decimal" placeholder="0" value={price} onChange={(e) => setPrice(e.target.value)} aria-invalid={priceInvalid} />
          </Field>
        )}
        {plan && (
          <label className="flex min-h-11 items-center gap-2 text-lg">
            <input type="checkbox" className="size-5" checked={active} onChange={(e) => setActive(e.target.checked)} />
            {t("admin.planActive")}
          </label>
        )}
        <ErrorText error={write.error} />
        <Button type="submit" disabled={write.isPending || (!plan && !keyValid) || priceInvalid}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
