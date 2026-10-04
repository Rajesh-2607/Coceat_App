import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../../api/client";
import {
  useCreateGrade,
  useCreateLocation,
  useCreateUnit,
  useGrades,
  useLocations,
  useUnits,
  useUpdateGrade,
  useUpdateLocation,
} from "../../api/hooks";
import { Badge, Button, EmptyState, ErrorText, Field, Input, LinkButton, QueryBoundary, Select, Sheet } from "../../lib/ui";
import { useName } from "../../lib/useName";

type Location = Schemas["LocationOut"];
type Kind = Schemas["LocationCreate"]["kind"];
const KINDS: NonNullable<Kind>[] = ["shop", "godown", "cold_storage", "other"];

export function SetupTab({ canManageLocations, canManageCatalog }: { canManageLocations: boolean; canManageCatalog: boolean }) {
  return (
    <div className="space-y-8">
      <LocationsSection canManage={canManageLocations} />
      <UnitsSection canManage={canManageCatalog} />
      <GradesSection canManage={canManageCatalog} />
    </div>
  );
}

function SectionHeader({ title, onAdd, addLabel }: { title: string; onAdd?: () => void; addLabel: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-xl font-bold">{title}</h2>
      {onAdd && (
        <Button className="!w-auto !min-h-11 !text-base" onClick={onAdd}>
          + {addLabel}
        </Button>
      )}
    </div>
  );
}

/* ---- locations -------------------------------------------------------------------------------------- */

function LocationsSection({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const name = useName();
  const locations = useLocations();
  const [editing, setEditing] = useState<Location | "new" | null>(null);
  return (
    <section className="space-y-3">
      <SectionHeader title={t("locations.title")} addLabel={t("locations.add")} onAdd={canManage ? () => setEditing("new") : undefined} />
      <QueryBoundary query={locations}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("locations.empty")}</EmptyState>
          ) : (
            <ul className="divide-y rounded-2xl border border-slate-200 bg-white">
              {rows.map((l) => (
                <li key={l.id} className="flex min-h-14 items-center justify-between gap-2 px-4">
                  <div className="min-w-0">
                    <p className="truncate text-lg">{name(l)}</p>
                    <p className="text-sm text-slate-500">{t(`locations.kinds.${l.kind}`)}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    {!l.is_active && <Badge tone="warn">{t("common.inactive")}</Badge>}
                    {canManage && <LinkButton onClick={() => setEditing(l)}>{t("common.edit")}</LinkButton>}
                  </div>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {editing && <LocationSheet location={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function LocationSheet({ location, onClose }: { location: Location | null; onClose: () => void }) {
  const { t } = useTranslation();
  const create = useCreateLocation();
  const update = useUpdateLocation(location?.id ?? "");
  const [nameEn, setNameEn] = useState(location?.name ?? "");
  const [nameTa, setNameTa] = useState(location?.name_ta ?? "");
  const [kind, setKind] = useState<NonNullable<Kind>>(location?.kind ?? "shop");
  const [active, setActive] = useState(location?.is_active ?? true);
  const write = location ? update : create;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (location) update.mutate({ name: nameEn, name_ta: nameTa || null, kind, is_active: active }, { onSuccess: onClose });
    else create.mutate({ name: nameEn, name_ta: nameTa || null, kind }, { onSuccess: onClose });
  }

  return (
    <Sheet title={location ? t("locations.edit") : t("locations.add")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("locations.name")}>
          <Input required maxLength={80} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("locations.nameTa")}>
          <Input maxLength={120} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <Field label={t("locations.kind")}>
          <Select value={kind} onChange={(e) => setKind(e.target.value as NonNullable<Kind>)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`locations.kinds.${k}`)}
              </option>
            ))}
          </Select>
        </Field>
        {location && (
          <label className="flex min-h-11 items-center gap-2 text-lg">
            <input type="checkbox" className="size-5" checked={active} onChange={(e) => setActive(e.target.checked)} />
            {t("common.active")}
          </label>
        )}
        <ErrorText error={write.error} />
        <Button type="submit" disabled={write.isPending}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- units ------------------------------------------------------------------------------------------ */

function UnitsSection({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const name = useName();
  const units = useUnits();
  const [adding, setAdding] = useState(false);
  return (
    <section className="space-y-3">
      <SectionHeader title={t("catalog.units")} addLabel={t("catalog.addUnit")} onAdd={canManage ? () => setAdding(true) : undefined} />
      <QueryBoundary query={units}>
        {(rows) => (
          <ul className="divide-y rounded-2xl border border-slate-200 bg-white">
            {rows.map((u) => (
              <li key={u.id} className="flex min-h-12 items-center justify-between gap-2 px-4">
                <span className="text-lg">{name(u)}</span>
                <span className="text-sm text-slate-500">
                  {u.code} · {u.kind === "weight" ? `${u.base_factor} g` : `${u.base_factor} ${t("units.pcs")}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
      {adding && <UnitSheet onClose={() => setAdding(false)} />}
    </section>
  );
}

function UnitSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const create = useCreateUnit();
  const [code, setCode] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [nameTa, setNameTa] = useState("");
  const [kind, setKind] = useState<Schemas["UnitCreate"]["kind"]>("weight");
  const [factor, setFactor] = useState("");
  const factorValue = /^\d+$/.test(factor) ? Number(factor) : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!factorValue) return;
    create.mutate({ code, name: nameEn, name_ta: nameTa || null, kind, base_factor: factorValue }, { onSuccess: onClose });
  }

  return (
    <Sheet title={t("catalog.addUnit")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("catalog.unitCode")} hint={t("catalog.unitCodeHint")}>
          <Input required maxLength={20} pattern="[a-z0-9_]+" value={code} onChange={(e) => setCode(e.target.value.toLowerCase())} />
        </Field>
        <Field label={t("catalog.name")}>
          <Input required maxLength={60} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("catalog.nameTa")}>
          <Input maxLength={100} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <Field label={t("catalog.kind")}>
          <Select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            <option value="weight">{t("catalog.kinds.weight")}</option>
            <option value="count">{t("catalog.kinds.count")}</option>
          </Select>
        </Field>
        <Field label={t("catalog.baseFactor")} hint={kind === "weight" ? t("catalog.baseFactorGrams") : t("catalog.baseFactorPieces")}>
          <Input required inputMode="numeric" value={factor} onChange={(e) => setFactor(e.target.value.replace(/\D/g, ""))} />
        </Field>
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending || !factorValue}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- grades ----------------------------------------------------------------------------------------- */

function GradesSection({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const name = useName();
  const grades = useGrades();
  const [adding, setAdding] = useState(false);
  return (
    <section className="space-y-3">
      <SectionHeader title={t("catalog.grades")} addLabel={t("catalog.addGrade")} onAdd={canManage ? () => setAdding(true) : undefined} />
      <QueryBoundary query={grades}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("catalog.noGrades")}</EmptyState>
          ) : (
            <ul className="divide-y rounded-2xl border border-slate-200 bg-white">
              {rows.map((g) => (
                <GradeRow key={g.id} grade={g} canManage={canManage} label={name(g)} />
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {adding && <GradeSheet onClose={() => setAdding(false)} />}
    </section>
  );
}

function GradeRow({ grade, canManage, label }: { grade: Schemas["GradeOut"]; canManage: boolean; label: string }) {
  const { t } = useTranslation();
  const update = useUpdateGrade(grade.id);
  return (
    <li className="flex min-h-12 items-center justify-between gap-2 px-4">
      <span className={`text-lg ${grade.is_active ? "" : "text-slate-400 line-through"}`}>{label}</span>
      {canManage && (
        <LinkButton disabled={update.isPending} onClick={() => update.mutate({ is_active: !grade.is_active })}>
          {grade.is_active ? t("common.deactivate") : t("common.activate")}
        </LinkButton>
      )}
    </li>
  );
}

function GradeSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const create = useCreateGrade();
  const [nameEn, setNameEn] = useState("");
  const [nameTa, setNameTa] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate({ name: nameEn, name_ta: nameTa || null }, { onSuccess: onClose });
  }
  return (
    <Sheet title={t("catalog.addGrade")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("catalog.name")}>
          <Input required maxLength={40} value={nameEn} onChange={(e) => setNameEn(e.target.value)} autoFocus />
        </Field>
        <Field label={t("catalog.nameTa")}>
          <Input maxLength={80} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
