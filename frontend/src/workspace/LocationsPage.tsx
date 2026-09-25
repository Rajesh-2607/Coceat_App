import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { newIdempotencyKey, useCreateLocation, useLocations } from "../api/hooks";
import { Button, ErrorText, Field, Input, Loading } from "../lib/ui";

type Kind = NonNullable<Schemas["LocationCreate"]["kind"]>;
const KINDS: Kind[] = ["shop", "godown", "cold_storage", "other"];

export function LocationsPage({ canManage }: { canManage: boolean }) {
  const { t, i18n } = useTranslation();
  const locations = useLocations();
  const create = useCreateLocation();
  const [name, setName] = useState("");
  const [nameTa, setNameTa] = useState("");
  const [kind, setKind] = useState<Kind>("shop");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { body: { name, name_ta: nameTa || null, kind }, key: newIdempotencyKey() },
      {
        onSuccess: () => {
          setName("");
          setNameTa("");
        },
      },
    );
  }

  return (
    <section className="space-y-6">
      <h1 className="text-2xl font-bold">{t("locations.title")}</h1>
      {locations.isPending ? (
        <Loading />
      ) : locations.error ? (
        <ErrorText error={locations.error} />
      ) : locations.data.length === 0 ? (
        <p className="text-slate-500">{t("locations.empty")}</p>
      ) : (
        <ul className="divide-y rounded-xl border">
          {locations.data.map((l) => (
            <li key={l.id} className="flex min-h-14 items-center justify-between px-4">
              <span className="text-lg">{(i18n.language === "ta" && l.name_ta) || l.name}</span>
              <span className="text-sm text-slate-500">{t(`locations.kinds.${l.kind}`)}</span>
            </li>
          ))}
        </ul>
      )}

      {canManage && (
        <form onSubmit={onSubmit} className="space-y-4 rounded-xl bg-slate-50 p-4">
          <h2 className="text-lg font-semibold">{t("locations.add")}</h2>
          <Field label={t("locations.name")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required />
          </Field>
          <Field label={t("locations.nameTa")}>
            <Input value={nameTa} onChange={(e) => setNameTa(e.target.value)} maxLength={120} />
          </Field>
          <Field label={t("locations.kind")}>
            <select
              className="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-lg"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`locations.kinds.${k}`)}
                </option>
              ))}
            </select>
          </Field>
          <ErrorText error={create.error} />
          <Button type="submit" disabled={create.isPending}>
            {t("common.save")}
          </Button>
        </form>
      )}
    </section>
  );
}
