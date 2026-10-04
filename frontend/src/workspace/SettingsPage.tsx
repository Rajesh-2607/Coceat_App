import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useChangePassword } from "../api/hooks";
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader } from "../lib/ui";
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
      <ChangePasswordCard />
    </section>
  );
}

function ChangePasswordCard() {
  const { t } = useTranslation();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [done, setDone] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
          setDone(true);
        },
      },
    );
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-3">
        <p className="font-medium text-slate-700">{t("settings.password")}</p>
        <Field label={t("settings.currentPassword")}>
          <Input
            type="password"
            autoComplete="current-password"
            maxLength={200}
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </Field>
        <Field label={t("settings.newPassword")} hint={t("login.passwordHint")}>
          <Input
            type="password"
            autoComplete="new-password"
            minLength={10}
            maxLength={200}
            value={next}
            onChange={(e) => {
              setNext(e.target.value);
              setDone(false);
            }}
            required
          />
        </Field>
        <ErrorText error={change.error} />
        {done && <p className="text-green-700">{t("settings.passwordChanged")}</p>}
        <Button type="submit" disabled={change.isPending || !current || next.length < 10}>
          {t("settings.changePassword")}
        </Button>
      </form>
    </Card>
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
