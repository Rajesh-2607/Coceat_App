import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { formatMoney, parseRupees } from "../lib/format";
import { Input, LinkButton, SecondaryButton, Select } from "../lib/ui";

export type Method = Schemas["SalePaymentIn"]["method"];
export const METHODS: Method[] = ["cash", "upi", "card", "bank", "cheque", "other"];

export type PayRow = { method: Method; amount: string };

/** Valid rows as API payments; null when any filled-in amount is not a valid rupee amount above zero. */
export function rowsToPayments(rows: PayRow[]): { method: Method; amount_paise: number }[] | null {
  const out: { method: Method; amount_paise: number }[] = [];
  for (const r of rows) {
    if (r.amount.trim() === "") continue;
    const paise = parseRupees(r.amount);
    if (paise === null || paise <= 0) return null;
    out.push({ method: r.method, amount_paise: paise });
  }
  return out;
}

/** "How was it paid?": one or more (method, amount) rows. Whatever is left over is shown as credit by the parent. */
export function PaymentRows({
  rows,
  onChange,
  total,
}: {
  rows: PayRow[];
  onChange: (rows: PayRow[]) => void;
  total: number;
}) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<PayRow>) => onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex gap-2">
          <Select className="!w-32 shrink-0" aria-label={t("pay.method")} value={r.method} onChange={(e) => set(i, { method: e.target.value as Method })}>
            {METHODS.map((m) => (
              <option key={m} value={m}>
                {t(`pay.methods.${m}`)}
              </option>
            ))}
          </Select>
          <Input
            inputMode="decimal"
            placeholder="0"
            aria-label={t("pay.amount")}
            value={r.amount}
            onChange={(e) => set(i, { amount: e.target.value })}
          />
          {rows.length > 1 && (
            <LinkButton type="button" aria-label={t("common.remove")} onClick={() => onChange(rows.filter((_, idx) => idx !== i))}>
              ✕
            </LinkButton>
          )}
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        {METHODS.slice(0, 3).map((m) => (
          <SecondaryButton
            key={m}
            type="button"
            className="!min-h-11"
            onClick={() => onChange([{ method: m, amount: total > 0 ? String(total / 100) : "" }])}
          >
            {t(`pay.full_${m}`)}
          </SecondaryButton>
        ))}
        <SecondaryButton type="button" className="!min-h-11" onClick={() => onChange([{ method: "cash", amount: "" }])}>
          {t("pay.allCredit")}
        </SecondaryButton>
        <SecondaryButton type="button" className="!min-h-11" onClick={() => onChange([...rows, { method: "upi", amount: "" }])}>
          + {t("pay.split")}
        </SecondaryButton>
      </div>
    </div>
  );
}

export function paidTotal(rows: PayRow[]): number {
  const payments = rowsToPayments(rows);
  return payments ? payments.reduce((sum, p) => sum + p.amount_paise, 0) : 0;
}

export function CreditLine({ total, paid }: { total: number; paid: number }) {
  const { t } = useTranslation();
  const left = total - paid;
  if (left === 0) return <p className="text-emerald-700">✓ {t("pay.settled")}</p>;
  if (left < 0) return <p className="text-rose-700">{t("pay.tooMuch", { amount: formatMoney(-left) })}</p>;
  return <p className="text-amber-700">{t("pay.onCredit", { amount: formatMoney(left) })}</p>;
}
