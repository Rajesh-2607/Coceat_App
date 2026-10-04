import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAdminPlans, useAdminPlatformSettings, useAdminUpdatePlatformSettings } from "../api/hooks";
import { Button, Card, ErrorText, Field, Input, PageHeader, QueryBoundary, Select } from "../lib/ui";

type Tab = "platform" | "billing" | "notifications";
const NOTIFICATION_EVENTS = ["trial_expiring", "payment_failure", "setup_completed", "module_toggled"] as const;

/** Platform-wide defaults applied to every new business. No payment gateway or email/Slack dispatch is wired
 * up yet — these are the preferences that would drive one, stored for when they are. */
export function SettingsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("platform");
  const settings = useAdminPlatformSettings();

  return (
    <section className="space-y-4">
      <PageHeader title={t("admin.settings")} subtitle={t("admin.settingsHint")} />
      <div className="flex gap-2">
        {(["platform", "billing", "notifications"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`min-h-11 rounded-full px-4 text-base font-medium ${tab === k ? "bg-violet-700 text-white" : "bg-white ring-1 ring-slate-200"}`}
          >
            {t(`admin.settingsTabs.${k}`)}
          </button>
        ))}
      </div>
      <QueryBoundary query={settings}>
        {(s) =>
          tab === "platform" ? (
            <PlatformTab settings={s} />
          ) : tab === "billing" ? (
            <BillingTab settings={s} />
          ) : (
            <NotificationsTab key={JSON.stringify(s.notification_prefs)} settings={s} />
          )
        }
      </QueryBoundary>
    </section>
  );
}

type Settings = NonNullable<ReturnType<typeof useAdminPlatformSettings>["data"]>;

function PlatformTab({ settings }: { settings: Settings }) {
  const { t } = useTranslation();
  const update = useAdminUpdatePlatformSettings();
  const [platformName, setPlatformName] = useState(settings.platform_name);
  const [supportEmail, setSupportEmail] = useState(settings.support_email);
  const [currency, setCurrency] = useState(settings.default_currency);
  const [trialDays, setTrialDays] = useState(String(settings.default_trial_days));

  function submit(e: FormEvent) {
    e.preventDefault();
    update.mutate({
      platform_name: platformName,
      support_email: supportEmail,
      default_currency: currency,
      default_trial_days: Number(trialDays) || settings.default_trial_days,
    });
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4">
        <h2 className="text-lg font-bold">{t("admin.platformIdentity")}</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("admin.platformName")}>
            <Input required maxLength={120} value={platformName} onChange={(e) => setPlatformName(e.target.value)} />
          </Field>
          <Field label={t("admin.supportEmail")}>
            <Input required type="email" maxLength={200} value={supportEmail} onChange={(e) => setSupportEmail(e.target.value)} />
          </Field>
          <Field label={t("admin.defaultCurrency")}>
            <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="INR">INR (₹)</option>
            </Select>
          </Field>
          <Field label={t("admin.defaultTrialDays")}>
            <Input required inputMode="numeric" value={trialDays} onChange={(e) => setTrialDays(e.target.value.replace(/\D/g, ""))} />
          </Field>
        </div>
        <ErrorText error={update.error} />
        <Button type="submit" className="!w-auto" disabled={update.isPending}>
          {t("admin.saveChanges")}
        </Button>
      </form>
    </Card>
  );
}

function BillingTab({ settings }: { settings: Settings }) {
  const { t } = useTranslation();
  const plans = useAdminPlans(false);
  const update = useAdminUpdatePlatformSettings();
  const [defaultPlan, setDefaultPlan] = useState(settings.default_plan_key ?? "");
  const [invoicePrefix, setInvoicePrefix] = useState(settings.invoice_prefix);
  const [gstPct, setGstPct] = useState(String(settings.gst_rate_bp / 100));
  const [graceDays, setGraceDays] = useState(String(settings.grace_period_days));

  function submit(e: FormEvent) {
    e.preventDefault();
    update.mutate({
      default_plan_key: defaultPlan || null,
      invoice_prefix: invoicePrefix,
      gst_rate_bp: Math.round(Number(gstPct) * 100),
      grace_period_days: Number(graceDays) || 0,
    });
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4">
        <h2 className="text-lg font-bold">{t("admin.billingDefaults")}</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("admin.defaultPlan")}>
            <Select value={defaultPlan} onChange={(e) => setDefaultPlan(e.target.value)}>
              <option value="">{t("common.none")}</option>
              {(plans.data ?? []).map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("admin.invoicePrefix")}>
            <Input maxLength={20} value={invoicePrefix} onChange={(e) => setInvoicePrefix(e.target.value)} />
          </Field>
          <Field label={t("admin.gstRateOnSubscription")}>
            <Input inputMode="decimal" value={gstPct} onChange={(e) => setGstPct(e.target.value)} />
          </Field>
          <Field label={t("admin.gracePeriodDays")}>
            <Input inputMode="numeric" value={graceDays} onChange={(e) => setGraceDays(e.target.value.replace(/\D/g, ""))} />
          </Field>
        </div>
        <ErrorText error={update.error} />
        <Button type="submit" className="!w-auto" disabled={update.isPending}>
          {t("admin.saveChanges")}
        </Button>
      </form>
    </Card>
  );
}

function NotificationsTab({ settings }: { settings: Settings }) {
  const { t } = useTranslation();
  const update = useAdminUpdatePlatformSettings();
  const [prefs, setPrefs] = useState(settings.notification_prefs);

  function toggle(event: string, channel: "email" | "slack") {
    const current = prefs[event] ?? { email: true, slack: true };
    const next = { ...prefs, [event]: { ...current, [channel]: !current[channel] } };
    setPrefs(next);
    update.mutate({ notification_prefs: next });
  }

  return (
    <Card className="space-y-1">
      <h2 className="mb-2 text-lg font-bold">{t("admin.notifications")}</h2>
      <p className="mb-3 text-sm text-slate-500">{t("admin.notificationsHint")}</p>
      <ErrorText error={update.error} />
      <ul className="divide-y">
        {NOTIFICATION_EVENTS.map((event) => {
          const pref = prefs[event] ?? { email: true, slack: true };
          return (
            <li key={event} className="flex min-h-14 items-center justify-between gap-3 py-2">
              <span className="font-medium">{t(`admin.notificationEvent.${event}`)}</span>
              <div className="flex gap-3 text-sm">
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" className="size-4" checked={pref.email} onChange={() => toggle(event, "email")} />
                  {t("admin.channelEmail")}
                </label>
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" className="size-4" checked={pref.slack} onChange={() => toggle(event, "slack")} />
                  {t("admin.channelSlack")}
                </label>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
