import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { newIdempotencyKey, type Schemas } from "../../api/client";
import { useCreateBill, useGrades, useParties, useProducts, useStockBalances, useUnits } from "../../api/hooks";
import { formatMoney, formatQuantity, parseRupees } from "../../lib/format";
import { billTotals, gstState } from "../../lib/pricing";
import { parseQtyToBase } from "../../lib/quantity";
import { Button, Card, ErrorText, Field, Input, LinkButton, PageHeader, SecondaryButton, Select, Textarea } from "../../lib/ui";
import { useName, useQuantityLabels } from "../../lib/useName";
import { useCurrentLocation } from "../location";
import { CreditLine, PaymentRows, paidTotal, rowsToPayments, type PayRow } from "../PaymentRows";
import { EMPTY_ITEM, findProduct, ItemFields, type ItemValue } from "../stock/StockFields";

type Context = Schemas["WorkspaceContextOut"];

type CartLine = {
  id: number;
  item: ItemValue;
  unitId: string;
  qty: string;
  price: string;
};

/** The counter screen: pick goods, see the total, say how it was paid, make the bill. Phone-first. */
export function SellPage({ context }: { context: Context }) {
  const { t } = useTranslation();
  const name = useName();
  const labels = useQuantityLabels();
  const navigate = useNavigate();
  const { locationId, locations } = useCurrentLocation();
  const products = useProducts();
  const grades = useGrades();
  const units = useUnits();
  const customers = useParties("customers", "");
  const create = useCreateBill();

  const [where, setWhere] = useState("");
  const shopId = locationId ?? (where || (locations.length === 1 ? locations[0]!.id : ""));
  const balances = useStockBalances(shopId || null);

  const [partyId, setPartyId] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [draft, setDraft] = useState<CartLine>({ id: 0, item: EMPTY_ITEM, unitId: "", qty: "", price: "" });
  const [rows, setRows] = useState<PayRow[]>([{ method: "cash", amount: "" }]);
  const [payTouched, setPayTouched] = useState(false); // until the trader edits payment, "paid in cash in full" is assumed
  const [note, setNote] = useState("");
  const [nextId, setNextId] = useState(1);
  // ONE key per bill: a second tap or a retry after a bad network reuses it, so the server bills once
  const [billKey, setBillKey] = useState(() => newIdempotencyKey());

  const productList = products.data ?? [];
  const unitList = units.data ?? [];
  const party = (customers.data ?? []).find((c) => c.id === partyId);
  const sellerState = gstState(context.business.gstin);
  const buyerState = gstState(party?.gstin) ?? sellerState;
  const interState = Boolean(sellerState && buyerState && sellerState !== buyerState);

  const draftProduct = findProduct(productList, draft.item.productId);
  const unitsForDraft = unitList.filter((u) => u.is_active && draftProduct && u.kind === draftProduct.kind);
  const draftUnit = unitList.find((u) => u.id === draft.unitId);
  const draftQty = draftUnit ? parseQtyToBase(draft.qty, draftUnit.base_factor) : null;
  const draftPrice = parseRupees(draft.price);
  const available = useMemo(() => {
    if (!draftProduct) return null;
    const rowsFor = (balances.data ?? []).filter(
      (b) =>
        b.product_id === draftProduct.id &&
        (draft.item.varietyId === "" || b.variety_id === draft.item.varietyId) &&
        (draft.item.gradeId === "" || b.grade_id === draft.item.gradeId),
    );
    return rowsFor.reduce((sum, b) => sum + b.quantity, 0);
  }, [balances.data, draftProduct, draft.item.varietyId, draft.item.gradeId]);

  function pickProduct(item: ItemValue) {
    const p = findProduct(productList, item.productId);
    setDraft({
      ...draft,
      item,
      unitId: p?.unit_id ?? "",
      price: p?.default_price_paise != null ? String(p.default_price_paise / 100) : "",
    });
  }

  function addLine() {
    if (!draftProduct || draftQty === null || draftPrice === null) return;
    setCart([...cart, { ...draft, id: nextId }]);
    setNextId(nextId + 1);
    setDraft({ id: 0, item: EMPTY_ITEM, unitId: "", qty: "", price: "" });
    changed();
  }

  /** Any change to what is being billed starts a new bill (a new key), so an old failed attempt can't be replayed. */
  function changed() {
    setBillKey(newIdempotencyKey());
    create.reset();
  }

  const priced = cart.map((l) => {
    const p = findProduct(productList, l.item.productId)!;
    const unit = unitList.find((u) => u.id === l.unitId)!;
    const quantity = parseQtyToBase(l.qty, unit.base_factor)!;
    const price = parseRupees(l.price)!;
    return { line: l, product: p, unit, quantity, price };
  });
  const totals = billTotals(
    priced.map((p) => ({ quantityBase: p.quantity, baseFactor: p.unit.base_factor, unitPricePaise: p.price, gstRateBp: p.product.gst_rate_bp })),
    interState,
  );
  const effectiveRows: PayRow[] = payTouched ? rows : [{ method: "cash", amount: totals.total > 0 ? String(totals.total / 100) : "" }];
  const payments = rowsToPayments(effectiveRows);
  const paid = paidTotal(effectiveRows);
  const credit = totals.total - paid;
  const needsCustomer = credit > 0 && partyId === "";
  const overLimit = Boolean(party && party.credit_limit_paise != null && credit > 0 && party.balance_paise + credit > party.credit_limit_paise);
  const ready = cart.length > 0 && totals.total > 0 && shopId !== "" && payments !== null && credit >= 0 && !needsCustomer;

  function submit() {
    if (!ready || payments === null) return;
    create.mutate(
      {
        location_id: shopId,
        party_id: partyId || null,
        lines: priced.map((p) => ({
          product_id: p.product.id,
          variety_id: p.line.item.varietyId || null,
          grade_id: p.line.item.gradeId || null,
          unit_id: p.unit.id,
          quantity: p.quantity,
          unit_price_paise: p.price,
        })),
        payments,
        note: note || null,
      },
      { onSuccess: (bill) => navigate(`/w/bills/${bill.id}`, { state: { justCreated: true } }) },
      billKey,
    );
  }

  const describe = (l: CartLine) => {
    const p = findProduct(productList, l.item.productId);
    const v = p?.varieties.find((x) => x.id === l.item.varietyId);
    const g = (grades.data ?? []).find((x) => x.id === l.item.gradeId);
    return [p ? name(p) : "…", v ? name(v) : null, g ? name(g) : null].filter(Boolean).join(" · ");
  };

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.sell")} />

      <Card className="space-y-3">
        {locationId === null && locations.length > 1 && (
          <Field label={t("stock.location")}>
            <Select value={where} onChange={(e) => { setWhere(e.target.value); changed(); }}>
              <option value="">{t("common.choose")}</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {name(l)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label={t("sell.customer")}>
          <Select value={partyId} onChange={(e) => { setPartyId(e.target.value); changed(); }}>
            <option value="">{t("sell.walkIn")}</option>
            {(customers.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {name(c)}
                {c.balance_paise > 0 ? ` (${t("parties.theyOwe")} ${formatMoney(c.balance_paise)})` : ""}
              </option>
            ))}
          </Select>
        </Field>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-lg font-bold">{t("sell.addItem")}</h2>
        <ItemFields value={draft.item} onChange={pickProduct} products={productList} grades={grades.data ?? []} />
        {draftProduct && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("sell.unit")}>
                <Select value={draft.unitId} onChange={(e) => setDraft({ ...draft, unitId: e.target.value })}>
                  {unitsForDraft.map((u) => (
                    <option key={u.id} value={u.id}>
                      {name(u)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={`${t("sell.price")} (₹)`}>
                <Input inputMode="decimal" placeholder="0" value={draft.price} onChange={(e) => setDraft({ ...draft, price: e.target.value })} />
              </Field>
            </div>
            <Field
              label={`${t("stock.quantity")}${draftUnit ? ` (${draftUnit.code})` : ""}`}
              hint={available !== null && shopId ? t("sell.inStock", { qty: formatQuantity(available, draftProduct.kind, labels) }) : undefined}
            >
              <Input inputMode="decimal" placeholder="0" value={draft.qty} onChange={(e) => setDraft({ ...draft, qty: e.target.value })} />
            </Field>
            <Button type="button" onClick={addLine} disabled={draftQty === null || draftPrice === null}>
              + {t("sell.add")}
            </Button>
          </>
        )}
      </Card>

      {cart.length > 0 && (
        <Card className="space-y-2">
          <h2 className="text-lg font-bold">{t("sell.items")}</h2>
          <ul className="divide-y">
            {priced.map((p) => {
              const amount = billTotals(
                [{ quantityBase: p.quantity, baseFactor: p.unit.base_factor, unitPricePaise: p.price, gstRateBp: 0 }],
                false,
              ).taxable;
              return (
                <li key={p.line.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-lg font-semibold">{describe(p.line)}</p>
                    <p className="text-sm text-slate-500">
                      {p.line.qty} {p.unit.code} × {formatMoney(p.price)}
                      {p.product.gst_rate_bp > 0 ? ` + ${p.product.gst_rate_bp / 100}% GST` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <p className="text-lg font-bold">{formatMoney(amount)}</p>
                    <LinkButton type="button" aria-label={t("common.remove")} onClick={() => { setCart(cart.filter((c) => c.id !== p.line.id)); changed(); }}>
                      ✕
                    </LinkButton>
                  </div>
                </li>
              );
            })}
          </ul>
          <TotalsBlock totals={totals} />
        </Card>
      )}

      {cart.length > 0 && (
        <Card className="space-y-3">
          <h2 className="text-lg font-bold">{t("sell.payment")}</h2>
          <PaymentRows
            rows={effectiveRows}
            onChange={(r) => {
              setRows(r);
              setPayTouched(true);
              changed();
            }}
            total={totals.total}
          />
          <CreditLine total={totals.total} paid={paid} />
          {needsCustomer && <p className="text-rose-700">{t("errors.credit_needs_customer")}</p>}
          {overLimit && <p className="text-rose-700">{t("errors.credit_limit_exceeded")}</p>}
          <Field label={t("stock.note")}>
            <Textarea
              maxLength={300}
              value={note}
              onChange={(e) => {
                setNote(e.target.value);
                changed();
              }}
            />
          </Field>
          <ErrorText error={create.error} />
          <Button type="button" onClick={submit} disabled={!ready || create.isPending}>
            {create.isPending ? t("common.loading") : `${t("sell.makeBill")} · ${formatMoney(totals.total)}`}
          </Button>
          <SecondaryButton type="button" className="w-full" onClick={() => {
              setCart([]);
              setRows([{ method: "cash", amount: "" }]);
              setPayTouched(false);
              changed();
            }}>
            {t("sell.clear")}
          </SecondaryButton>
        </Card>
      )}
    </section>
  );
}

export function TotalsBlock({ totals }: { totals: { taxable: number; cgst: number; sgst: number; igst: number; roundOff: number; total: number } }) {
  const { t } = useTranslation();
  const row = (label: string, value: string, strong = false) => (
    <div className={`flex justify-between ${strong ? "text-xl font-bold" : "text-slate-600"}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
  return (
    <div className="space-y-1 border-t pt-2">
      {totals.cgst + totals.sgst + totals.igst > 0 && row(t("bill.taxable"), formatMoney(totals.taxable))}
      {totals.cgst > 0 && row("CGST", formatMoney(totals.cgst))}
      {totals.sgst > 0 && row("SGST", formatMoney(totals.sgst))}
      {totals.igst > 0 && row("IGST", formatMoney(totals.igst))}
      {totals.roundOff !== 0 && row(t("bill.roundOff"), `${totals.roundOff > 0 ? "+" : "−"}${formatMoney(Math.abs(totals.roundOff))}`)}
      {row(t("bill.total"), formatMoney(totals.total), true)}
    </div>
  );
}
