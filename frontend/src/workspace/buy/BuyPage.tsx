import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { newIdempotencyKey, type Schemas } from "../../api/client";
import { useCreatePurchase, useGrades, useParties, useProducts, usePurchase, usePurchases, useUnits, useVoidPurchase } from "../../api/hooks";
import { todayIst } from "../../lib/dates";
import { formatDateTime, formatMoney, parseRupees } from "../../lib/format";
import { lineAmount } from "../../lib/pricing";
import { baseToUnitText, parseQtyToBase } from "../../lib/quantity";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, SecondaryButton, Select, Sheet, Textarea } from "../../lib/ui";
import { useName } from "../../lib/useName";
import { useCurrentLocation } from "../location";
import { CreditLine, PaymentRows, paidTotal, rowsToPayments, type PayRow } from "../PaymentRows";
import { EMPTY_ITEM, findProduct, ItemFields, LocationSelect, type ItemValue } from "../stock/StockFields";

type Context = Schemas["WorkspaceContextOut"];
type Purchase = Schemas["PurchaseOut"];

export function BuyPage({ context }: { context: Context }) {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const purchases = usePurchases({ q: q.trim() || undefined });
  const [creating, setCreating] = useState(false);
  const canCreate = context.permissions.includes("purchases.create");
  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.buy")} subtitle={t("buy.subtitle")} />
      {canCreate && <Button onClick={() => setCreating(true)}>🚚 {t("buy.new")}</Button>}
      <Input type="search" placeholder={t("buy.search")} aria-label={t("buy.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <QueryBoundary query={purchases}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("buy.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((p) => (
                <li key={p.id}>
                  <Link to={`/w/buy/${p.id}`} className="block">
                    <Card className="flex items-center justify-between gap-3 active:bg-violet-50">
                      <div className="min-w-0">
                        <p className="truncate text-lg font-semibold">{p.supplier_name}</p>
                        <p className="truncate text-sm text-slate-500">
                          {p.purchase_number} · {formatDateTime(p.created_at, i18n.language)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className={`text-lg font-bold ${p.status === "void" ? "text-slate-400 line-through" : ""}`}>{formatMoney(p.total_paise)}</p>
                        {p.status === "void" ? (
                          <Badge tone="bad">{t("bills.statuses.void")}</Badge>
                        ) : p.paid_paise < p.total_paise ? (
                          <Badge tone="warn">{t("buy.owed", { amount: formatMoney(p.total_paise - p.paid_paise) })}</Badge>
                        ) : (
                          <Badge tone="good">{t("bills.paid")}</Badge>
                        )}
                      </div>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {creating && <NewPurchaseSheet onClose={() => setCreating(false)} />}
    </section>
  );
}

/* ---- new purchase ----------------------------------------------------------------------------------- */

type Line = { item: ItemValue; unitId: string; qty: string; cost: string };
const blank = (): Line => ({ item: EMPTY_ITEM, unitId: "", qty: "", cost: "" });

function NewPurchaseSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const name = useName();
  const { locationId, locations } = useCurrentLocation();
  const products = useProducts();
  const grades = useGrades();
  const units = useUnits();
  const suppliers = useParties("suppliers", "");
  const create = useCreatePurchase();
  const [supplier, setSupplier] = useState("");
  const [where, setWhere] = useState(locationId ?? (locations.length === 1 ? locations[0]!.id : ""));
  const [billNo, setBillNo] = useState("");
  const [date, setDate] = useState(todayIst());
  const [lines, setLines] = useState<Line[]>([blank()]);
  const [rows, setRows] = useState<PayRow[]>([{ method: "cash", amount: "" }]);
  const [key] = useState(() => newIdempotencyKey());

  if (!products.data || !grades.data || !units.data) return <Sheet title={t("buy.new")} onClose={onClose}><p className="p-6 text-center">{t("common.loading")}</p></Sheet>;
  const productList = products.data;
  const unitList = units.data;

  const parsed = lines.map((l) => {
    const p = findProduct(productList, l.item.productId);
    const unit = unitList.find((u) => u.id === l.unitId);
    const quantity = unit ? parseQtyToBase(l.qty, unit.base_factor) : null;
    const cost = parseRupees(l.cost);
    const amount = unit && quantity !== null && cost !== null ? lineAmount(quantity, unit.base_factor, cost) : null;
    return { l, p, unit, quantity, cost, amount };
  });
  const total = parsed.reduce((s, x) => s + (x.amount ?? 0), 0);
  const payments = rowsToPayments(rows);
  const paid = paidTotal(rows);
  const ready = supplier !== "" && where !== "" && payments !== null && paid <= total && total > 0 && parsed.every((x) => x.amount !== null);

  const setLine = (i: number, patch: Partial<Line>) => setLines(lines.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready || payments === null) return;
    create.mutate(
      {
        supplier_id: supplier,
        location_id: where,
        purchase_date: date,
        supplier_bill_no: billNo || null,
        lines: parsed.map((x) => ({
          product_id: x.p!.id,
          variety_id: x.l.item.varietyId || null,
          grade_id: x.l.item.gradeId || null,
          unit_id: x.unit!.id,
          quantity: x.quantity!,
          unit_cost_paise: x.cost!,
        })),
        payments,
      },
      { onSuccess: onClose },
      key,
    );
  }

  return (
    <Sheet title={t("buy.new")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("nav.suppliers")}>
          <Select required value={supplier} onChange={(e) => setSupplier(e.target.value)}>
            <option value="">{t("common.choose")}</option>
            {(suppliers.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {name(s)}
              </option>
            ))}
          </Select>
        </Field>
        <LocationSelect label={t("buy.receiveAt")} value={where} onChange={setWhere} locations={locations} />
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("buy.supplierBillNo")}>
            <Input maxLength={40} value={billNo} onChange={(e) => setBillNo(e.target.value)} />
          </Field>
          <Field label={t("buy.date")}>
            <Input type="date" max={todayIst()} value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </div>
        {parsed.map((x, i) => {
          const unitsFor = unitList.filter((u) => u.is_active && x.p && u.kind === x.p.kind);
          return (
            <div key={i} className="space-y-3 rounded-2xl bg-slate-50 p-3">
              <ItemFields
                value={x.l.item}
                onChange={(item) => {
                  const p = findProduct(productList, item.productId);
                  setLine(i, { item, unitId: p?.unit_id ?? "" });
                }}
                products={productList}
                grades={grades.data}
              />
              {x.p && (
                <div className="grid grid-cols-3 gap-2">
                  <Field label={t("sell.unit")}>
                    <Select value={x.l.unitId} onChange={(e) => setLine(i, { unitId: e.target.value })}>
                      {unitsFor.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.code}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={t("stock.quantity")}>
                    <Input inputMode="decimal" placeholder="0" value={x.l.qty} onChange={(e) => setLine(i, { qty: e.target.value })} />
                  </Field>
                  <Field label={`${t("buy.cost")} ₹`}>
                    <Input inputMode="decimal" placeholder="0" value={x.l.cost} onChange={(e) => setLine(i, { cost: e.target.value })} />
                  </Field>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="font-semibold">{x.amount !== null ? formatMoney(x.amount) : ""}</span>
                {lines.length > 1 && <LinkButton type="button" onClick={() => setLines(lines.filter((_, idx) => idx !== i))}>{t("common.remove")}</LinkButton>}
              </div>
            </div>
          );
        })}
        <SecondaryButton type="button" className="w-full" onClick={() => setLines([...lines, blank()])}>
          + {t("stock.addLine")}
        </SecondaryButton>
        <div className="flex justify-between text-xl font-bold">
          <span>{t("bill.total")}</span>
          <span>{formatMoney(total)}</span>
        </div>
        <Field label={t("buy.paidNow")}>
          <PaymentRows rows={rows} onChange={setRows} total={total} />
        </Field>
        <CreditLine total={total} paid={paid} />
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending || !ready}>
          {t("buy.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- one purchase ----------------------------------------------------------------------------------- */

export function PurchaseDetailPage({ context }: { context: Context }) {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const purchase = usePurchase(id);
  return (
    <section className="space-y-4">
      <Link to="/w/buy" className="inline-flex min-h-11 items-center font-medium text-violet-700">
        ← {t("nav.buy")}
      </Link>
      <QueryBoundary query={purchase}>{(p) => <PurchaseView purchase={p} canVoid={context.permissions.includes("purchases.void")} />}</QueryBoundary>
    </section>
  );
}

function PurchaseView({ purchase, canVoid }: { purchase: Purchase; canVoid: boolean }) {
  const { t, i18n } = useTranslation();
  const [voiding, setVoiding] = useState(false);
  const active = purchase.status === "active";
  return (
    <>
      <PageHeader
        title={purchase.purchase_number}
        subtitle={`${purchase.supplier_name} · ${formatDateTime(purchase.created_at, i18n.language)}`}
        actions={<Badge tone={active ? "good" : "bad"}>{t(`bills.statuses.${purchase.status}`)}</Badge>}
      />
      {!active && (
        <Card className="border-rose-200 bg-rose-50">
          <p className="font-semibold text-rose-800">{t("bills.cancelledBecause", { reason: purchase.void_reason })}</p>
        </Card>
      )}
      <Card className="space-y-2">
        {purchase.supplier_bill_no && <p className="text-slate-500">{t("buy.supplierBillNo")}: {purchase.supplier_bill_no}</p>}
        <ul className="divide-y">
          {purchase.lines.map((ln) => (
            <li key={ln.id} className="flex items-start justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="text-lg font-semibold">{(i18n.language === "ta" && ln.description_ta) || ln.description}</p>
                <p className="text-sm text-slate-500">
                  {baseToUnitText(ln.quantity_base, ln.unit_base_factor)} {ln.unit_code} × {formatMoney(ln.unit_cost_paise)}
                </p>
              </div>
              <p className="shrink-0 text-lg font-bold">{formatMoney(ln.amount_paise)}</p>
            </li>
          ))}
        </ul>
        <div className="flex justify-between text-xl font-bold">
          <span>{t("bill.total")}</span>
          <span>{formatMoney(purchase.total_paise)}</span>
        </div>
        <div className="flex justify-between text-slate-600">
          <span>{t("bills.paidNow")}</span>
          <span>{formatMoney(purchase.paid_paise)}</span>
        </div>
        {purchase.credit_paise > 0 && (
          <div className="flex justify-between font-semibold text-amber-700">
            <span>{t("buy.stillOwed")}</span>
            <span>{formatMoney(purchase.credit_paise)}</span>
          </div>
        )}
      </Card>
      {active && canVoid && <SecondaryButton className="w-full" onClick={() => setVoiding(true)}>🚫 {t("buy.cancel")}</SecondaryButton>}
      {voiding && <VoidSheet purchase={purchase} onClose={() => setVoiding(false)} />}
    </>
  );
}

function VoidSheet({ purchase, onClose }: { purchase: Purchase; onClose: () => void }) {
  const { t } = useTranslation();
  const voidPurchase = useVoidPurchase(purchase.id);
  const [reason, setReason] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    voidPurchase.mutate(reason, { onSuccess: onClose });
  }
  return (
    <Sheet title={t("buy.cancel")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-slate-600">{t("buy.cancelHint")}</p>
        <Field label={t("stock.reason")}>
          <Textarea required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={voidPurchase.error} />
        <Button type="submit" disabled={voidPurchase.isPending || reason.trim().length < 3}>
          {t("buy.cancel")}
        </Button>
      </form>
    </Sheet>
  );
}
