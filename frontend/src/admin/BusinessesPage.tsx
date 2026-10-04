import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { Schemas } from "../api/client";
import { useAdminBusinesses, useAdminCompleteSetup, useAdminCreateBusiness, useAdminVerticals } from "../api/hooks";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, Select, Sheet } from "../lib/ui";
import { useName } from "../lib/useName";
import { ModulePicker } from "./ModulePicker";

type ModuleList = NonNullable<Schemas["BusinessCreate"]["enabled_modules"]>;
type Business = Schemas["AdminBusinessOut"];
type Filter = "all" | "active" | "trial" | "setup_pending";

function filterBusinesses(rows: Business[], filter: Filter, q: string): Business[] {
  let list = rows;
  if (filter === "active") list = list.filter((b) => b.status === "active" && b.setup_completed_at !== null);
  if (filter === "trial") list = list.filter((b) => b.subscription_status === "trial");
  if (filter === "setup_pending") list = list.filter((b) => b.setup_completed_at === null);
  const needle = q.trim().toLowerCase();
  if (needle) {
    list = list.filter(
      (b) =>
        b.name.toLowerCase().includes(needle) ||
        (b.name_ta ?? "").includes(needle) ||
        b.vertical_key.toLowerCase().includes(needle),
    );
  }
  return list;
}

export function BusinessesPage() {
  const { t } = useTranslation();
  const name = useName();
  const businesses = useAdminBusinesses();
  const completeSetup = useAdminCompleteSetup();
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");

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
        {(rows) => {
          const filtered = filterBusinesses(rows, filter, q);

          return (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex gap-1 rounded-full bg-slate-100 p-1">
                  {(["all", "active", "trial", "setup_pending"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFilter(f)}
                      className={`min-h-9 rounded-full px-3 text-sm font-medium ${
                        filter === f ? "bg-violet-700 text-white" : "text-slate-600"
                      }`}
                    >
                      {t(`admin.businessFilter.${f}`)}
                    </button>
                  ))}
                </div>
                <Input
                  className="!w-auto min-w-56 flex-1"
                  placeholder={t("admin.searchBusinesses")}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>

              {filtered.length === 0 ? (
                <EmptyState>{t("admin.noBusinesses")}</EmptyState>
              ) : (
                <Card className="space-y-0 overflow-x-auto !p-0">
                  <div className="border-b border-slate-100 p-4">
                    <h2 className="text-lg font-bold">{t("admin.businessDirectory")}</h2>
                    <p className="text-sm text-slate-500">{t("admin.matchingBusinesses", { count: filtered.length })}</p>
                  </div>
                  <table className="w-full min-w-[820px] text-left text-sm">
                    <thead>
                      <tr className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        <th className="px-4 py-2">{t("admin.colBusiness")}</th>
                        <th className="px-4 py-2">{t("admin.colType")}</th>
                        <th className="px-4 py-2">{t("admin.colMarket")}</th>
                        <th className="px-4 py-2">{t("admin.colShops")}</th>
                        <th className="px-4 py-2">{t("admin.colModules")}</th>
                        <th className="px-4 py-2">{t("admin.colUsers")}</th>
                        <th className="px-4 py-2">{t("admin.colPlan")}</th>
                        <th className="px-4 py-2">{t("admin.colStatus")}</th>
                        <th className="px-4 py-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((b: Business) => (
                        <tr key={b.id} className="border-t border-slate-100">
                          <td className="px-4 py-3 font-semibold">{name(b)}</td>
                          <td className="px-4 py-3 text-slate-500">{b.vertical_key}</td>
                          <td className="px-4 py-3 text-slate-500">{b.address ?? "—"}</td>
                          <td className="px-4 py-3">{b.location_count}</td>
                          <td className="px-4 py-3">{b.enabled_modules.length}</td>
                          <td className="px-4 py-3">{b.member_count}</td>
                          <td className="px-4 py-3 text-slate-500">
                            {b.plan_name ? (name({ name: b.plan_name, name_ta: b.plan_name_ta ?? undefined }) as string) : "—"}
                          </td>
                          <td className="px-4 py-3">
                            <Badge tone={b.status === "active" ? "good" : "bad"}>{t(`admin.status.${b.status}`)}</Badge>
                          </td>
                          <td className="px-4 py-3 text-right">
                            {b.setup_completed_at === null ? (
                              <LinkButton
                                className="!min-h-9"
                                disabled={completeSetup.isPending}
                                onClick={() => completeSetup.mutate(b.id)}
                              >
                                {t("admin.markSetupDone")}
                              </LinkButton>
                            ) : (
                              <Link to={`/admin/businesses/${b.id}`} className="font-medium text-violet-700">
                                {t("admin.configure")} →
                              </Link>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}
            </>
          );
        }}
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
