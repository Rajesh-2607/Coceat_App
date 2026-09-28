import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import {
  useAdjustParty,
  useAdjustPartyCrates,
  useParty,
  usePartyCrates,
  usePartyLedger,
  useUpdateParty,
  type PartyKind,
} from "../../api/hooks";
import { formatDateTime, formatMoney, parseRupees } from "../../lib/format";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, SecondaryButton, Sheet, StatTile, Textarea } from "../../lib/ui";
import { useName } from "../../lib/useName";

type Context = Schemas["WorkspaceContextOut"];
type Party = Schemas["PartyOut"];

export function PartyDetailPage({ kind, context }: { kind: PartyKind; context: Context }) {
  const { t } = useTranslation();
  const name = useName();
  const { id = "" } = useParams();
  const party = useParty(kind, id);
  return (
    <section className="space-y-4">
      <Link to={`/w/${kind}`} className="inline-flex min-h-11 items-center font-medium text-violet-700">
        ← {t(`nav.${kind}`)}
      </Link>
      <QueryBoundary query={party}>
        {(p) => (
          <>
            <PartyHeader kind={kind} party={p} canManage={context.permissions.includes("parties.manage")} title={name(p)} />
            <Tabs kind={kind} party={p} context={context} />
          </>
        )}
      </QueryBoundary>
    </section>
  );
}

function PartyHeader({ kind, party, canManage, title }: { kind: PartyKind; party: Party; canManage: boolean; title: string }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const balance = party.balance_paise;
  return (
    <>
      <PageHeader
        title={title}
        subtitle={[party.phone, party.address].filter(Boolean).join(" · ") || undefined}
        actions={canManage ? <SecondaryButton onClick={() => setEditing(true)}>{t("common.edit")}</SecondaryButton> : undefined}
      />
      <div className="grid grid-cols-2 gap-3">
        <StatTile
          label={balance >= 0 ? t("parties.theyOwe") : t("parties.youOwe")}
          value={formatMoney(Math.abs(balance))}
          tone={balance > 0 ? "warn" : balance < 0 ? "bad" : "neutral"}
        />
        <StatTile label={t("parties.cratesHeldLabel")} value={String(party.crates_held)} tone="brand" />
      </div>
      {party.credit_limit_paise != null && (
        <p className="text-slate-600">
          {t("parties.creditLimit")}: {formatMoney(party.credit_limit_paise)}
          {balance > party.credit_limit_paise && <Badge tone="bad">{t("parties.overLimit")}</Badge>}
        </p>
      )}
      {!party.is_active && <Badge tone="warn">{t("common.inactive")}</Badge>}
      {editing && <EditPartySheet kind={kind} party={party} onClose={() => setEditing(false)} />}
    </>
  );
}

function Tabs({ kind, party, context }: { kind: PartyKind; party: Party; context: Context }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"ledger" | "crates">("ledger");
  const canCrates = context.permissions.includes("crates.view") && context.business.enabled_modules.includes("stock");
  const canManage = context.permissions.includes("parties.manage");
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {(["ledger", ...(canCrates ? (["crates"] as const) : [])] as ("ledger" | "crates")[]).map((k) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`min-h-11 rounded-full px-4 text-base font-medium ${tab === k ? "bg-violet-700 text-white" : "bg-white ring-1 ring-slate-200"}`}
          >
            {t(`parties.tabs.${k}`)}
          </button>
        ))}
      </div>
      {tab === "ledger" ? (
        <LedgerList kind={kind} party={party} canManage={canManage} />
      ) : (
        <CrateList kind={kind} party={party} canManage={context.permissions.includes("crates.manage")} />
      )}
    </div>
  );
}

/* ---- money ledger ----------------------------------------------------------------------------------- */

function LedgerList({ kind, party, canManage }: { kind: PartyKind; party: Party; canManage: boolean }) {
  const { t, i18n } = useTranslation();
  const ledger = usePartyLedger(kind, party.id);
  const [adjusting, setAdjusting] = useState(false);
  return (
    <div className="space-y-3">
      {canManage && <SecondaryButton className="w-full" onClick={() => setAdjusting(true)}>✏️ {t("parties.adjustBalance")}</SecondaryButton>}
      <QueryBoundary query={ledger}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("parties.noLedger")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((e) => (
                <li key={e.id}>
                  <Card className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold">{t(`parties.entryTypes.${e.entry_type}`, { defaultValue: e.entry_type })}</p>
                      <p className="text-sm text-slate-500">{formatDateTime(e.created_at, i18n.language)}</p>
                      {e.note && <p className="text-slate-600">{e.note}</p>}
                    </div>
                    <p className={`shrink-0 text-lg font-bold ${e.amount_paise > 0 ? "text-amber-600" : "text-emerald-600"}`}>
                      {e.amount_paise > 0 ? "+" : "−"}
                      {formatMoney(Math.abs(e.amount_paise))}
                    </p>
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {adjusting && <AdjustSheet kind={kind} party={party} onClose={() => setAdjusting(false)} />}
    </div>
  );
}

function AdjustSheet({ kind, party, onClose }: { kind: PartyKind; party: Party; onClose: () => void }) {
  const { t } = useTranslation();
  const adjust = useAdjustParty(kind, party.id);
  const [direction, setDirection] = useState<"they" | "you">("they");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const value = parseRupees(amount);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!value) return;
    // "they owe more" adds to the balance; "I owe more" (or they owe less) subtracts
    adjust.mutate({ amount_paise: direction === "they" ? value : -value, note }, { onSuccess: onClose });
  }

  return (
    <Sheet title={t("parties.adjustBalance")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-slate-600">{t("parties.adjustHint")}</p>
        <div className="flex gap-2" role="radiogroup">
          {(["they", "you"] as const).map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={direction === d}
              onClick={() => setDirection(d)}
              className={`min-h-12 flex-1 rounded-xl border text-base font-medium ${direction === d ? "border-violet-700 bg-violet-50 text-violet-700" : "border-slate-300"}`}
            >
              {d === "they" ? t("parties.increase") : t("parties.decrease")}
            </button>
          ))}
        </div>
        <Field label={t("parties.amount")}>
          <Input required inputMode="decimal" placeholder="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label={t("stock.reason")} hint={t("stock.reasonHint")}>
          <Textarea required minLength={3} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={adjust.error} />
        <Button type="submit" disabled={adjust.isPending || !value || note.trim().length < 3}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- crates ----------------------------------------------------------------------------------------- */

function CrateList({ kind, party, canManage }: { kind: PartyKind; party: Party; canManage: boolean }) {
  const { t, i18n } = useTranslation();
  const crates = usePartyCrates(kind, party.id);
  const [adjusting, setAdjusting] = useState(false);
  return (
    <div className="space-y-3">
      {canManage && <SecondaryButton className="w-full" onClick={() => setAdjusting(true)}>✏️ {t("parties.adjustCrates")}</SecondaryButton>}
      <QueryBoundary query={crates}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("crates.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((e) => (
                <li key={e.id}>
                  <Card className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold">{t(`crates.entryTypes.${e.entry_type}`, { defaultValue: e.entry_type })}</p>
                      <p className="text-sm text-slate-500">{formatDateTime(e.created_at, i18n.language)}</p>
                      {e.note && <p className="text-slate-600">{e.note}</p>}
                    </div>
                    <p className={`shrink-0 text-lg font-bold ${e.quantity > 0 ? "text-amber-600" : "text-emerald-600"}`}>
                      {e.quantity > 0 ? "+" : "−"}
                      {Math.abs(e.quantity)}
                    </p>
                  </Card>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {adjusting && <CrateAdjustSheet kind={kind} party={party} onClose={() => setAdjusting(false)} />}
    </div>
  );
}

function CrateAdjustSheet({ kind, party, onClose }: { kind: PartyKind; party: Party; onClose: () => void }) {
  const { t } = useTranslation();
  const adjust = useAdjustPartyCrates(kind, party.id);
  const [sign, setSign] = useState<1 | -1>(-1);
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const value = /^\d+$/.test(qty) && Number(qty) > 0 ? Number(qty) : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!value) return;
    adjust.mutate({ quantity: sign * value, note }, { onSuccess: onClose });
  }

  return (
    <Sheet title={t("parties.adjustCrates")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="flex gap-2" role="radiogroup">
          {([-1, 1] as const).map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={sign === s}
              onClick={() => setSign(s)}
              className={`min-h-12 flex-1 rounded-xl border text-base font-medium ${sign === s ? "border-violet-700 bg-violet-50 text-violet-700" : "border-slate-300"}`}
            >
              {s === 1 ? t("parties.holdsMore") : t("parties.holdsLess")}
            </button>
          ))}
        </div>
        <Field label={t("crates.count")}>
          <Input required inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))} />
        </Field>
        <Field label={t("stock.reason")} hint={t("stock.reasonHint")}>
          <Textarea required minLength={3} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={adjust.error} />
        <Button type="submit" disabled={adjust.isPending || !value || note.trim().length < 3}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- edit ------------------------------------------------------------------------------------------- */

function EditPartySheet({ kind, party, onClose }: { kind: PartyKind; party: Party; onClose: () => void }) {
  const { t } = useTranslation();
  const update = useUpdateParty(kind, party.id);
  const [nameEn, setNameEn] = useState(party.name);
  const [nameTa, setNameTa] = useState(party.name_ta ?? "");
  const [phone, setPhone] = useState(party.phone ?? "");
  const [address, setAddress] = useState(party.address ?? "");
  const [gstin, setGstin] = useState(party.gstin ?? "");
  const [limit, setLimit] = useState(party.credit_limit_paise != null ? String(party.credit_limit_paise / 100) : "");
  const [active, setActive] = useState(party.is_active);
  const limitValue = limit.trim() === "" ? null : parseRupees(limit);
  const invalid = limit.trim() !== "" && limitValue === null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (invalid) return;
    update.mutate(
      {
        name: nameEn,
        name_ta: nameTa || null,
        phone: phone || null,
        address: address || null,
        gstin: gstin || null,
        credit_limit_paise: kind === "customers" ? limitValue : null,
        is_active: active,
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Sheet title={t("common.edit")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("parties.name")}>
          <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
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
          <Field label={t("parties.creditLimit")}>
            <Input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} />
          </Field>
        )}
        <label className="flex min-h-11 items-center gap-2 text-lg">
          <input type="checkbox" className="size-5" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {t("common.active")}
        </label>
        <ErrorText error={update.error} />
        <Button type="submit" disabled={update.isPending || invalid}>
          {t("common.save")}
        </Button>
        <LinkButton type="button" className="w-full" onClick={onClose}>
          {t("common.cancel")}
        </LinkButton>
      </form>
    </Sheet>
  );
}
