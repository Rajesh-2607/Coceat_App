import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { billPdfUrl, useBill, useBillReturns, useReturnGoods, useVoidBill } from "../../api/hooks";
import { formatDateTime, formatMoney, parseRupees } from "../../lib/format";
import { baseToUnitText, parseQtyToBase } from "../../lib/quantity";
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, QueryBoundary, SecondaryButton, Select, Sheet, Textarea } from "../../lib/ui";
import { METHODS, type Method } from "../PaymentRows";
import { TotalsBlock } from "../sell/SellPage";

type Bill = Schemas["BillOut"];
type Context = Schemas["WorkspaceContextOut"];

export function BillDetailPage({ context }: { context: Context }) {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const bill = useBill(id);
  const created = (useLocation().state as { justCreated?: boolean } | null)?.justCreated === true;
  return (
    <section className="space-y-4">
      <Link to="/w/bills" className="inline-flex min-h-11 items-center font-medium text-violet-700">
        ← {t("nav.bills")}
      </Link>
      {created && <p className="rounded-2xl bg-emerald-50 p-3 text-lg text-emerald-800">✓ {t("bills.created")}</p>}
      <QueryBoundary query={bill}>{(b) => <BillView bill={b} context={context} />}</QueryBoundary>
    </section>
  );
}

function BillView({ bill, context }: { bill: Bill; context: Context }) {
  const { t, i18n } = useTranslation();
  const can = (perm: string) => context.permissions.includes(perm);
  const [sheet, setSheet] = useState<"void" | "return" | null>(null);
  const returns = useBillReturns(bill.id);
  const hasReturns = (returns.data?.length ?? 0) > 0;
  const active = bill.status === "active";
  const exact = { taxable: bill.taxable_paise, cgst: bill.cgst_paise, sgst: bill.sgst_paise, igst: bill.igst_paise, roundOff: bill.round_off_paise, total: bill.total_paise };
  const share = `https://wa.me/${bill.party_phone ? `91${bill.party_phone.replace(/\D/g, "").slice(-10)}` : ""}?text=${encodeURIComponent(
    t("bills.shareText", { seller: bill.seller_name, number: bill.bill_number, amount: formatMoney(bill.total_paise) }),
  )}`;

  return (
    <>
      <PageHeader
        title={bill.bill_number}
        subtitle={`${bill.doc_type === "tax_invoice" ? t("bills.taxInvoice") : t("bills.billOfSupply")} · ${formatDateTime(bill.created_at, i18n.language)}`}
        actions={<Badge tone={active ? "good" : "bad"}>{t(`bills.statuses.${bill.status}`)}</Badge>}
      />
      {!active && (
        <Card className="border-rose-200 bg-rose-50">
          <p className="font-semibold text-rose-800">{t("bills.cancelledBecause", { reason: bill.void_reason })}</p>
        </Card>
      )}
      <Card className="space-y-1">
        <p className="text-lg font-semibold">{bill.party_name ?? t("sell.walkIn")}</p>
        {bill.party_phone && <p className="text-slate-500">{bill.party_phone}</p>}
        {bill.party_gstin && <p className="text-slate-500">GSTIN {bill.party_gstin}</p>}
      </Card>

      <Card className="space-y-2">
        <ul className="divide-y">
          {bill.lines.map((ln) => (
            <li key={ln.id} className="flex items-start justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="text-lg font-semibold">{(i18n.language === "ta" && ln.description_ta) || ln.description}</p>
                <p className="text-sm text-slate-500">
                  {baseToUnitText(ln.quantity_base, ln.unit_base_factor)} {ln.unit_code} × {formatMoney(ln.unit_price_paise)}
                  {ln.gst_rate_bp > 0 ? ` + ${ln.gst_rate_bp / 100}% GST` : ""}
                </p>
                {ln.returned_base > 0 && (
                  <p className="text-sm text-amber-700">{t("bills.returnedQty", { qty: baseToUnitText(ln.returned_base, ln.unit_base_factor), unit: ln.unit_code })}</p>
                )}
              </div>
              <p className="shrink-0 text-lg font-bold">{formatMoney(ln.total_paise)}</p>
            </li>
          ))}
        </ul>
        <TotalsBlock totals={exact} />
        <div className="flex justify-between text-slate-600">
          <span>{t("bills.paidNow")}</span>
          <span>{formatMoney(bill.paid_paise)}</span>
        </div>
        {bill.credit_paise > 0 && (
          <div className="flex justify-between font-semibold text-amber-700">
            <span>{t("bills.onCredit")}</span>
            <span>{formatMoney(bill.credit_paise)}</span>
          </div>
        )}
      </Card>

      {bill.payments.length > 0 && (
        <Card className="space-y-1">
          <h2 className="text-lg font-bold">{t("bills.payments")}</h2>
          {bill.payments.map((p) => (
            <div key={p.id} className="flex justify-between text-slate-700">
              <span>
                {t(`pay.methods.${p.method}`)} {p.reversal_of ? `(${t("stock.reversed")})` : ""}
              </span>
              <span className={p.direction === "out" ? "text-rose-600" : ""}>
                {p.direction === "out" ? "−" : ""}
                {formatMoney(p.amount_paise)}
              </span>
            </div>
          ))}
        </Card>
      )}

      {hasReturns && (
        <Card className="space-y-1">
          <h2 className="text-lg font-bold">{t("bills.returns")}</h2>
          {returns.data?.map((r) => (
            <div key={r.id} className="flex justify-between text-slate-700">
              <span>{r.return_number} · {r.reason}</span>
              <span>{formatMoney(r.total_paise)}</span>
            </div>
          ))}
        </Card>
      )}

      <Card className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <a className="flex min-h-12 items-center justify-center rounded-xl bg-violet-700 px-3 text-center font-semibold text-white" href={billPdfUrl(bill.id, "a4", i18n.language)} target="_blank" rel="noreferrer">
            🖨️ {t("bills.pdfA4")}
          </a>
          <a className="flex min-h-12 items-center justify-center rounded-xl border border-slate-300 px-3 text-center font-semibold" href={billPdfUrl(bill.id, "thermal", i18n.language)} target="_blank" rel="noreferrer">
            🧾 {t("bills.pdfThermal")}
          </a>
        </div>
        <a className="flex min-h-12 items-center justify-center rounded-xl border border-emerald-600 px-3 text-center font-semibold text-emerald-700" href={share} target="_blank" rel="noreferrer">
          💬 {t("bills.whatsapp")}
        </a>
        {active && (
          <div className="grid grid-cols-2 gap-2">
            {can("bills.return") && <SecondaryButton onClick={() => setSheet("return")}>↩️ {t("bills.return")}</SecondaryButton>}
            {can("bills.void") && !hasReturns && <SecondaryButton onClick={() => setSheet("void")}>🚫 {t("bills.cancelBill")}</SecondaryButton>}
          </div>
        )}
      </Card>

      {sheet === "void" && <VoidSheet bill={bill} onClose={() => setSheet(null)} />}
      {sheet === "return" && <ReturnSheet bill={bill} onClose={() => setSheet(null)} />}
    </>
  );
}

function VoidSheet({ bill, onClose }: { bill: Bill; onClose: () => void }) {
  const { t } = useTranslation();
  const voidBill = useVoidBill(bill.id);
  const [reason, setReason] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    voidBill.mutate(reason, { onSuccess: onClose });
  }
  return (
    <Sheet title={t("bills.cancelBill")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-slate-600">{t("bills.cancelHint")}</p>
        <Field label={t("stock.reason")}>
          <Textarea required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={voidBill.error} />
        <Button type="submit" disabled={voidBill.isPending || reason.trim().length < 3}>
          {t("bills.cancelBill")}
        </Button>
      </form>
    </Sheet>
  );
}

function ReturnSheet({ bill, onClose }: { bill: Bill; onClose: () => void }) {
  const { t } = useTranslation();
  const ret = useReturnGoods(bill.id);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [restock, setRestock] = useState(true);
  const [reason, setReason] = useState("");
  const [refund, setRefund] = useState("");
  const [method, setMethod] = useState<Method>("cash");

  const lines = bill.lines
    .map((ln) => {
      const left = ln.quantity_base - ln.returned_base;
      const base = parseQtyToBase(qty[ln.id] ?? "", ln.unit_base_factor);
      return { ln, left, base, tooMany: base !== null && base > left };
    })
    .filter((x) => x.left > 0);
  const chosen = lines.filter((x) => x.base !== null && !x.tooMany);
  const refundPaise = refund.trim() === "" ? 0 : parseRupees(refund);
  const walkIn = bill.party_id === null;
  const ready = chosen.length > 0 && !lines.some((x) => x.tooMany) && refundPaise !== null && reason.trim().length >= 3;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready || refundPaise === null) return;
    ret.mutate(
      {
        lines: chosen.map((x) => ({ bill_line_id: x.ln.id, quantity: x.base! })),
        reason,
        restock,
        refund_paise: refundPaise,
        refund_method: refundPaise > 0 ? method : null,
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Sheet title={t("bills.return")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {lines.map(({ ln, left, tooMany }) => (
          <Field
            key={ln.id}
            label={`${(ln.description)} (${t("bills.canReturn", { qty: baseToUnitText(left, ln.unit_base_factor), unit: ln.unit_code })})`}
          >
            <Input
              inputMode="decimal"
              placeholder="0"
              aria-invalid={tooMany}
              value={qty[ln.id] ?? ""}
              onChange={(e) => setQty({ ...qty, [ln.id]: e.target.value })}
            />
          </Field>
        ))}
        <label className="flex min-h-11 items-center gap-2 text-lg">
          <input type="checkbox" className="size-5" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
          {t("bills.restock")}
        </label>
        <Field label={t("bills.refundNow")} hint={walkIn ? t("bills.walkInRefund") : t("bills.refundHint")}>
          <Input inputMode="decimal" placeholder="0" value={refund} onChange={(e) => setRefund(e.target.value)} />
        </Field>
        {refundPaise !== null && refundPaise > 0 && (
          <Field label={t("pay.method")}>
            <Select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {t(`pay.methods.${m}`)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label={t("stock.reason")}>
          <Textarea required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={ret.error} />
        <Button type="submit" disabled={ret.isPending || !ready}>
          {t("bills.return")}
        </Button>
      </form>
    </Sheet>
  );
}
