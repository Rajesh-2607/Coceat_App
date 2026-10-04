import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { useCreateParty, useParties, type PartyKind } from "../../api/hooks";
import { formatMoney, parseRupees } from "../../lib/format";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, PageHeader, QueryBoundary, Sheet } from "../../lib/ui";
import { useName } from "../../lib/useName";
import { BalanceDirection } from "./BalanceDirection";

type Context = Schemas["WorkspaceContextOut"];

export function PartiesPage({ kind, context }: { kind: PartyKind; context: Context }) {
  const { t } = useTranslation();
  const name = useName();
  const [q, setQ] = useState("");
  const parties = useParties(kind, q.trim());
  const [adding, setAdding] = useState(false);
  const canManage = context.permissions.includes("parties.manage");

  return (
    <section className="space-y-4">
      <PageHeader
        title={t(`nav.${kind}`)}
        actions={canManage ? <Button className="!w-auto" onClick={() => setAdding(true)}>+ {t(`parties.add_${kind}`)}</Button> : undefined}
      />
      <Input type="search" placeholder={t("parties.search")} aria-label={t("parties.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <QueryBoundary query={parties}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{q ? t("parties.noMatch") : t(`parties.empty_${kind}`)}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((p) => (
                <li key={p.id}>
                  <Link to={`/w/${kind}/${p.id}`} className="block">
                    <Card className="flex items-center justify-between gap-3 active:bg-violet-50">
                      <div className="min-w-0">
                        <p className="truncate text-lg font-semibold">{name(p)}</p>
                        {p.phone && <p className="text-sm text-slate-500">{p.phone}</p>}
                      </div>
                      <div className="shrink-0 text-right">
                        <p className={`text-lg font-bold ${p.balance_paise > 0 ? "text-amber-600" : p.balance_paise < 0 ? "text-rose-600" : "text-slate-400"}`}>
                          {formatMoney(Math.abs(p.balance_paise))}
                        </p>
                        {p.balance_paise !== 0 && (
                          <p className="text-sm text-slate-500">{p.balance_paise > 0 ? t("parties.theyOwe") : t("parties.youOwe")}</p>
                        )}
                        {p.crates_held > 0 && <Badge tone="brand">{t("parties.cratesHeld", { count: p.crates_held })}</Badge>}
                      </div>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {adding && <NewPartySheet kind={kind} onClose={() => setAdding(false)} />}
    </section>
  );
}

function NewPartySheet({ kind, onClose }: { kind: PartyKind; onClose: () => void }) {
  const { t } = useTranslation();
  const create = useCreateParty(kind);
  const [nameEn, setNameEn] = useState("");
  const [nameTa, setNameTa] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [gstin, setGstin] = useState("");
  const [limit, setLimit] = useState("");
  const [opening, setOpening] = useState("");
  // suppliers usually start as "I owe them", customers as "they owe me"
  const [owes, setOwes] = useState<"they" | "you">(kind === "customers" ? "they" : "you");

  const openingValue = opening.trim() === "" ? 0 : parseRupees(opening);
  const limitValue = limit.trim() === "" ? null : parseRupees(limit);
  const invalid = openingValue === null || (limit.trim() !== "" && limitValue === null);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (invalid) return;
    create.mutate(
      {
        name: nameEn,
        name_ta: nameTa || null,
        phone: phone || null,
        address: address || null,
        gstin: gstin || null,
        credit_limit_paise: kind === "customers" ? limitValue : null,
        opening_balance_paise: owes === "they" ? openingValue! : -openingValue!,
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Sheet title={t(`parties.add_${kind}`)} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("parties.name")}>
          <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} autoFocus />
        </Field>
        <Field label={t("parties.nameTa")}>
          <Input maxLength={200} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <Field label={t("parties.phone")}>
          <Input type="tel" inputMode="numeric" maxLength={14} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </Field>
        <Field label={t("parties.address")}>
          <Input maxLength={300} value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Field label={t("parties.gstin")}>
          <Input maxLength={15} value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase())} />
        </Field>
        {kind === "customers" && (
          <Field label={t("parties.creditLimit")} hint={t("parties.creditLimitHint")}>
            <Input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} />
          </Field>
        )}
        <Field label={t("parties.openingBalance")} hint={t("parties.openingHint")}>
          <Input inputMode="decimal" placeholder="0" value={opening} onChange={(e) => setOpening(e.target.value)} />
        </Field>
        <BalanceDirection value={owes} onChange={setOwes} />
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending || invalid}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
