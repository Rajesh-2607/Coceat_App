import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { Badge, Card, PageHeader } from "../lib/ui";
import { useName } from "../lib/useName";

/** Read-only for now: the business profile and modules are configured by the Cocreat team. */
export function SettingsPage({ context }: { context: Schemas["WorkspaceContextOut"] }) {
  const { t } = useTranslation();
  const name = useName();
  const b = context.business;
  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.settings")} subtitle={t("settings.managedByCocreat")} />
      <Card className="space-y-3">
        <Row label={t("settings.business")} value={name(b)} />
        <Row label={t("settings.gstin")} value={b.gstin ?? t("settings.noGstin")} />
        <Row label={t("settings.vertical")} value={b.vertical_key} />
        <Row label={t("settings.role")} value={t(`roles.${context.role}`)} />
      </Card>
      <Card className="space-y-2">
        <p className="font-medium text-slate-700">{t("settings.modules")}</p>
        <div className="flex flex-wrap gap-2">
          {b.enabled_modules.map((m) => (
            <Badge key={m} tone="brand">
              {t(`nav.${m}`, { defaultValue: m })}
            </Badge>
          ))}
        </div>
      </Card>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="text-lg font-medium">{value}</span>
    </div>
  );
}
