import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useAdminCreateVertical, useAdminUpdateVertical, useAdminVerticals } from "../api/hooks";
import { Badge, Button, Card, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, SecondaryButton, Sheet } from "../lib/ui";
import { useName } from "../lib/useName";
import { ModulePicker } from "./ModulePicker";

type Vertical = Schemas["VerticalOut"];

/** Trades (banana, vegetable, flower...) are configuration rows, not code: this is where new ones are added. */
export function ConfigurationPage() {
  const { t } = useTranslation();
  const name = useName();
  const verticals = useAdminVerticals();
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<Vertical | "new" | null>(null);

  return (
    <section className="space-y-4">
      <PageHeader title={t("admin.configuration")} subtitle={t("admin.configurationHint")} />
      <QueryBoundary query={verticals}>
        {(rows) => {
          const active = rows.find((v) => v.key === selected) ?? rows[0];
          return (
            <>
              <div className="flex flex-wrap items-center gap-2">
                {rows.map((v) => (
                  <button
                    key={v.key}
                    onClick={() => setSelected(v.key)}
                    className={`min-h-11 rounded-full px-4 text-base font-medium ${
                      active?.key === v.key ? "bg-violet-700 text-white" : "bg-white ring-1 ring-slate-200"
                    }`}
                  >
                    {name(v)}
                  </button>
                ))}
                <Button className="!w-auto" onClick={() => setEditing("new")}>
                  + {t("admin.newVertical")}
                </Button>
              </div>
              {active && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-slate-500">{active.key}</p>
                    <LinkButton onClick={() => setEditing(active)}>{t("common.edit")}</LinkButton>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <Card className="space-y-3">
                      <h2 className="text-lg font-bold">{t("admin.unitsAndProducts")}</h2>
                      <div>
                        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">{t("admin.referenceUnits")}</p>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {active.reference_units.length === 0 ? (
                            <span className="text-sm text-slate-400">{t("admin.noneSet")}</span>
                          ) : (
                            active.reference_units.map((u) => (
                              <Badge key={u} tone="neutral">
                                {u}
                              </Badge>
                            ))
                          )}
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">{t("admin.referenceVarieties")}</p>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {active.reference_varieties.length === 0 ? (
                            <span className="text-sm text-slate-400">{t("admin.noneSet")}</span>
                          ) : (
                            active.reference_varieties.map((v) => (
                              <Badge key={v} tone="neutral">
                                {v}
                              </Badge>
                            ))
                          )}
                        </div>
                      </div>
                      <p className="text-sm text-slate-500">{t("admin.referenceHint")}</p>
                    </Card>
                    <Card className="space-y-2">
                      <h2 className="text-lg font-bold">{t("admin.defaultModuleSet")}</h2>
                      <div className="flex flex-wrap gap-1.5">
                        {active.default_modules.length === 0 ? (
                          <span className="text-sm text-slate-400">{t("admin.noDefaultModules")}</span>
                        ) : (
                          active.default_modules.map((m) => (
                            <Badge key={m} tone="brand">
                              {t(`nav.${m}`, { defaultValue: m })}
                            </Badge>
                          ))
                        )}
                      </div>
                      <p className="text-sm text-slate-500">{t("admin.verticalModulesHint")}</p>
                    </Card>
                  </div>
                  {(active.workflow_steps.length > 0 || active.workflow_highlights.length > 0) && (
                    <Card className="space-y-3">
                      <h2 className="text-lg font-bold">{t("admin.workflowTemplate")}</h2>
                      {active.workflow_steps.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2">
                          {active.workflow_steps.map((s, i) => (
                            <div key={s.step} className="flex items-center gap-2">
                              <div className="min-w-32 rounded-xl border border-slate-200 px-3 py-2">
                                <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">
                                  {t("admin.stepN", { n: s.step })}
                                </p>
                                <p className="font-medium">{s.title}</p>
                              </div>
                              {i < active.workflow_steps.length - 1 && <span className="text-slate-400">›</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      {active.workflow_highlights.length > 0 && (
                        <div className="grid gap-3 md:grid-cols-3">
                          {active.workflow_highlights.map((h) => (
                            <div key={h.title} className="rounded-xl border border-slate-200 p-3">
                              <p className="font-medium text-emerald-700">✓ {h.title}</p>
                              <p className="text-sm text-slate-500">{h.description}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </Card>
                  )}
                </div>
              )}
            </>
          );
        }}
      </QueryBoundary>
      {editing && <VerticalSheet vertical={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function csv(list: string[]): string {
  return list.join(", ");
}

function parseCsv(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function VerticalSheet({ vertical, onClose }: { vertical: Vertical | null; onClose: () => void }) {
  const { t } = useTranslation();
  const create = useAdminCreateVertical();
  const update = useAdminUpdateVertical(vertical?.key ?? "");
  const [key, setKey] = useState(vertical?.key ?? "");
  const [nameEn, setNameEn] = useState(vertical?.name ?? "");
  const [nameTa, setNameTa] = useState(vertical?.name_ta ?? "");
  const [modules, setModules] = useState<string[]>(vertical?.default_modules ?? []);
  const [units, setUnits] = useState(csv(vertical?.reference_units ?? []));
  const [varieties, setVarieties] = useState(csv(vertical?.reference_varieties ?? []));
  const [steps, setSteps] = useState<string[]>(vertical?.workflow_steps.map((s) => s.title) ?? []);
  const [highlights, setHighlights] = useState<{ title: string; description: string }[]>(
    vertical?.workflow_highlights ?? [],
  );
  const write = vertical ? update : create;
  const keyValid = /^[a-z][a-z0-9_]*$/.test(key);

  function submit(e: FormEvent) {
    e.preventDefault();
    const body = {
      name: nameEn,
      name_ta: nameTa,
      default_modules: modules as Schemas["VerticalUpdate"]["default_modules"],
      reference_units: parseCsv(units),
      reference_varieties: parseCsv(varieties),
      workflow_steps: steps.filter(Boolean).map((title, i) => ({ step: i + 1, title })),
      workflow_highlights: highlights.filter((h) => h.title && h.description),
    };
    if (vertical) {
      update.mutate(body, { onSuccess: onClose });
    } else {
      if (!keyValid) return;
      create.mutate(
        { ...body, key, default_modules: modules as Schemas["VerticalCreate"]["default_modules"] },
        { onSuccess: onClose },
      );
    }
  }

  return (
    <Sheet title={vertical ? t("admin.editVertical") : t("admin.newVertical")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {!vertical && (
          <Field label={t("admin.verticalKey")} hint={t("admin.verticalKeyHint")}>
            <Input
              required
              maxLength={40}
              pattern="[a-z][a-z0-9_]*"
              value={key}
              onChange={(e) => setKey(e.target.value.toLowerCase())}
              aria-invalid={key.length > 0 && !keyValid}
              autoFocus
            />
          </Field>
        )}
        <Field label={t("admin.name")}>
          <Input required maxLength={80} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("admin.nameTa")}>
          <Input required maxLength={120} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <ModulePicker value={modules} onChange={setModules} />
        <Field label={t("admin.referenceUnits")} hint={t("admin.referenceCsvHint")}>
          <Input value={units} onChange={(e) => setUnits(e.target.value)} placeholder="crates, kg" />
        </Field>
        <Field label={t("admin.referenceVarieties")} hint={t("admin.referenceCsvHint")}>
          <Input value={varieties} onChange={(e) => setVarieties(e.target.value)} placeholder="Robusta, Poovan" />
        </Field>
        <div className="space-y-2">
          <p className="text-base font-medium text-slate-700">{t("admin.workflowSteps")}</p>
          {steps.map((s, i) => (
            <div key={i} className="flex gap-2">
              <Input
                value={s}
                onChange={(e) => setSteps(steps.map((x, j) => (j === i ? e.target.value : x)))}
                placeholder={t("admin.stepN", { n: i + 1 })}
              />
              <LinkButton type="button" onClick={() => setSteps(steps.filter((_, j) => j !== i))}>
                {t("common.remove")}
              </LinkButton>
            </div>
          ))}
          <SecondaryButton type="button" className="!w-auto" onClick={() => setSteps([...steps, ""])}>
            + {t("admin.addStep")}
          </SecondaryButton>
        </div>
        <div className="space-y-2">
          <p className="text-base font-medium text-slate-700">{t("admin.workflowHighlights")}</p>
          {highlights.map((h, i) => (
            <div key={i} className="space-y-1 rounded-xl border border-slate-200 p-2">
              <Input
                value={h.title}
                onChange={(e) => setHighlights(highlights.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))}
                placeholder={t("admin.highlightTitle")}
              />
              <Input
                value={h.description}
                onChange={(e) =>
                  setHighlights(highlights.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))
                }
                placeholder={t("admin.highlightDescription")}
              />
              <LinkButton type="button" onClick={() => setHighlights(highlights.filter((_, j) => j !== i))}>
                {t("common.remove")}
              </LinkButton>
            </div>
          ))}
          <SecondaryButton
            type="button"
            className="!w-auto"
            onClick={() => setHighlights([...highlights, { title: "", description: "" }])}
          >
            + {t("admin.addHighlight")}
          </SecondaryButton>
        </div>
        <ErrorText error={write.error} />
        <Button type="submit" disabled={write.isPending || (!vertical && !keyValid)}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
