import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { Schemas } from "../api/client";
import { useAdminBusinesses, useAdminCreateBusiness, useAdminVerticals } from "../api/hooks";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, PageHeader, QueryBoundary, Select, Sheet } from "../lib/ui";
import { useName } from "../lib/useName";
import { ModulePicker } from "./ModulePicker";

type ModuleList = NonNullable<Schemas["BusinessCreate"]["enabled_modules"]>;

export function BusinessesPage() {
  const { t } = useTranslation();
  const name = useName();
  const businesses = useAdminBusinesses();
  const [creating, setCreating] = useState(false);
  return (
    <section className="space-y-4">
      <PageHeader
        title={t("admin.businesses")}
        actions={
          <Button className="!w-auto" onClick={() => setCreating(true)}>
            + {t("admin.newBusiness")}
          </Button>
        }
      />
      <QueryBoundary query={businesses}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("admin.noBusinesses")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((b) => (
                <li key={b.id}>
                  <Link to={`/admin/businesses/${b.id}`} className="block">
                    <Card className="flex items-center justify-between gap-3 active:bg-violet-50">
                      <div className="min-w-0">
                        <p className="truncate text-lg font-semibold">{name(b)}</p>
                        <p className="text-sm text-slate-500">
                          {b.vertical_key} · {b.gstin ?? t("admin.noGstin")} · {t("admin.moduleCount", { count: b.enabled_modules.length })}
                        </p>
                      </div>
                      <Badge tone={b.status === "active" ? "good" : "bad"}>{t(`admin.status.${b.status}`)}</Badge>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {creating && <NewBusinessSheet onClose={() => setCreating(false)} />}
    </section>
  );
}

function NewBusinessSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const name = useName();
  const navigate = useNavigate();
  const verticals = useAdminVerticals();
  const create = useAdminCreateBusiness();
  const [nameEn, setNameEn] = useState("");
  const [nameTa, setNameTa] = useState("");
  const [gstin, setGstin] = useState("");
  const [vertical, setVertical] = useState("");
  const [modules, setModules] = useState<string[] | null>(null); // null = the vertical's defaults
  const template = verticals.data?.find((v) => v.key === vertical);
  const shown = modules ?? template?.default_modules ?? [];

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      {
        name: nameEn,
        name_ta: nameTa || null,
        gstin: gstin || null,
        vertical_key: vertical,
        enabled_modules: modules as ModuleList | null, // the API validates the module keys
      },
      { onSuccess: (b) => navigate(`/admin/businesses/${b.id}`) },
    );
  }

  return (
    <Sheet title={t("admin.newBusiness")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("admin.name")}>
          <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} autoFocus />
        </Field>
        <Field label={t("admin.nameTa")}>
          <Input maxLength={200} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <Field label={t("admin.vertical")}>
          <Select
            required
            value={vertical}
            onChange={(e) => {
              setVertical(e.target.value);
              setModules(null);
            }}
          >
            <option value="">{t("common.choose")}</option>
            {(verticals.data ?? []).map((v) => (
              <option key={v.key} value={v.key}>
                {name(v)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("admin.gstin")} hint={t("admin.gstinHint")}>
          <Input maxLength={15} value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase())} />
        </Field>
        {vertical && <ModulePicker value={shown} onChange={setModules} />}
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending || !vertical}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
