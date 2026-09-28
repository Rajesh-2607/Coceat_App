import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { useCreatePayment, useDayBook, useParties, usePayments, useReversePayment } from "../../api/hooks";
import { todayIst } from "../../lib/dates";
import { formatDateTime, formatMoney, parseRupees } from "../../lib/format";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, SecondaryButton, Select, Sheet, StatTile, Textarea } from "../../lib/ui";
import { useName } from "../../lib/useName";
import { METHODS, type Method } from "../PaymentRows";

type Context = Schemas["WorkspaceContextOut"];

export function MoneyPage({ context }: { context: Context }) {
  const { t, i18n } = useTranslation();
  const name = useName();
  const today = todayIst();
  const book = useDayBook(today);
  const payments = usePayments();
  const customers = useParties("customers", "", true);
  const suppliers = useParties("suppliers", "", true);
  const [recording, setRecording] = useState<"in" | "out" | null>(null);
  const [reversing, setReversing] = useState<string | null>(null);
  const canRecord = context.permissions.includes("money.record");

  const partyName = (id: string | null) => {
    if (!id) return "—";
    const p = customers.data?.find((c) => c.id === id) ?? suppliers.data?.find((s) => s.id === id);
    return p ? name(p) : "…";
  };

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.money")} subtitle={t("money.today")} />
      <QueryBoundary query={book}>
        {(b) => {
          const received = (b.payments ?? []).reduce((s, p) => s + p.received_paise, 0);
          const paid = (b.payments ?? []).reduce((s, p) => s + p.paid_paise, 0);
          return (
            <div className="grid grid-cols-2 gap-3">
              {b.sales && <StatTile label={t("money.salesToday")} value={formatMoney(b.sales.total_paise)} tone="good" hint={t("money.bills", { count: b.sales.bills })} />}
              <StatTile label={t("money.received")} value={formatMoney(received)} tone="brand" />
              <StatTile label={t("money.paidOut")} value={formatMoney(paid)} tone="bad" />
              {b.purchases && <StatTile label={t("money.boughtToday")} value={formatMoney(b.purchases.total_paise)} hint={t("money.entries", { count: b.purchases.purchases })} />}
              {(b.payments ?? []).map((p) => (
                <StatTile
                  key={p.method}
                  label={t(`pay.methods.${p.method}`)}
                  value={formatMoney(p.received_paise - p.paid_paise)}
                  hint={`+${formatMoney(p.received_paise)} / −${formatMoney(p.paid_paise)}`}
                />
              ))}
            </div>
          );
        }}
      </QueryBoundary>

      {canRecord && (
        <div className="grid grid-cols-2 gap-2">
          <Button onClick={() => setRecording("in")}>⬇️ {t("money.receive")}</Button>
          <SecondaryButton onClick={() => setRecording("out")}>⬆️ {t("money.pay")}</SecondaryButton>
        </div>
      )}

      <h2 className="text-xl font-bold">{t("money.history")}</h2>
      <QueryBoundary query={payments}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("money.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((p) => {
                const standalone = p.reference_type === null && p.reversal_of === null;
                const reversed = rows.some((r) => r.reversal_of === p.id);
                return (
                  <li key={p.id}>
                    <Card className="space-y-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-lg font-semibold">{partyName(p.party_id)}</p>
                        <p className={`shrink-0 text-lg font-bold ${p.direction === "in" ? "text-emerald-600" : "text-rose-600"}`}>
                          {p.direction === "in" ? "+" : "−"}
                          {formatMoney(p.amount_paise)}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
                        <Badge>{t(`pay.methods.${p.method}`)}</Badge>
                        {p.reference_type && <Badge tone="brand">{t(`money.refs.${p.reference_type}`, { defaultValue: p.reference_type })}</Badge>}
                        <span>{formatDateTime(p.created_at, i18n.language)}</span>
                        {reversed && <Badge tone="warn">{t("stock.reversed")}</Badge>}
                        {p.reversal_of && <Badge tone="warn">{t("money.reversal")}</Badge>}
                      </div>
                      {p.note && <p className="text-slate-600">{p.note}</p>}
                      {canRecord && standalone && !reversed && <LinkButton onClick={() => setReversing(p.id)}>{t("stock.reverse")}</LinkButton>}
                    </Card>
                  </li>
                );
              })}
            </ul>
          )
        }
      </QueryBoundary>
      <Link to="/w/customers" className="inline-flex min-h-11 items-center font-medium text-violet-700">
        {t("money.seeCustomers")} →
      </Link>
      {recording && <PaymentSheet direction={recording} customers={customers.data ?? []} suppliers={suppliers.data ?? []} onClose={() => setRecording(null)} />}
      {reversing && <ReverseSheet paymentId={reversing} onClose={() => setReversing(null)} />}
    </section>
  );
}

function PaymentSheet({
  direction,
  customers,
  suppliers,
  onClose,
}: {
  direction: "in" | "out";
  customers: Schemas["PartyOut"][];
  suppliers: Schemas["PartyOut"][];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const name = useName();
  const create = useCreatePayment();
  const [party, setParty] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<Method>("cash");
  const [note, setNote] = useState("");
  const paise = parseRupees(amount);
  // the natural list first: customers pay us, we pay suppliers
  const first = direction === "in" ? customers : suppliers;
  const second = direction === "in" ? suppliers : customers;
  const owed = [...customers, ...suppliers].find((p) => p.id === party)?.balance_paise ?? 0;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!paise) return;
    create.mutate({ party_id: party, direction, method, amount_paise: paise, note: note || null }, { onSuccess: onClose });
  }

  return (
    <Sheet title={direction === "in" ? t("money.receive") : t("money.pay")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("crates.party")}>
          <Select required value={party} onChange={(e) => setParty(e.target.value)}>
            <option value="">{t("common.choose")}</option>
            {[first, second].map((list, i) => (
              <optgroup key={i} label={(direction === "in") === (i === 0) ? t("nav.customers") : t("nav.suppliers")}>
                {list.map((p) => (
                  <option key={p.id} value={p.id}>
                    {name(p)}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </Field>
        {party && owed !== 0 && (
          <p className="text-slate-600">{owed > 0 ? t("parties.theyOwe") : t("parties.youOwe")}: <b>{formatMoney(Math.abs(owed))}</b></p>
        )}
        <Field label={`${t("parties.amount")}`}>
          <Input required inputMode="decimal" placeholder="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label={t("pay.method")}>
          <Select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
            {METHODS.map((m) => (
              <option key={m} value={m}>
                {t(`pay.methods.${m}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("stock.note")}>
          <Input maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending || !party || !paise}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

function ReverseSheet({ paymentId, onClose }: { paymentId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const reverse = useReversePayment();
  const [reason, setReason] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    reverse.mutate({ paymentId, reason }, { onSuccess: onClose });
  }
  return (
    <Sheet title={t("stock.reverse")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-slate-600">{t("money.reverseHint")}</p>
        <Field label={t("stock.reason")}>
          <Textarea required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={reverse.error} />
        <Button type="submit" disabled={reverse.isPending || reason.trim().length < 3}>
          {t("stock.reverse")}
        </Button>
      </form>
    </Sheet>
  );
}
