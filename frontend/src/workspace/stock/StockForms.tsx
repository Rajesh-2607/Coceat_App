import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useGrades, useProducts, useRecordOpening, useAdjustStock, useTransferStock, useRecordWastage, useReverseMovement } from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { parseQuantity } from "../../lib/format";
import { Button, ErrorText, Field, Input, LinkButton, Loading, SecondaryButton, Select, Sheet, Textarea } from "../../lib/ui";
import { useCurrentLocation } from "../location";
import { EMPTY_ITEM, findProduct, ItemFields, LocationSelect, QuantityField, type ItemValue } from "./StockFields";

type Props = { onClose: () => void };

/** Shared data for the stock forms; shows Loading until products and grades are there. */
function useFormData() {
  const products = useProducts();
  const grades = useGrades();
  const { locationId, locations } = useCurrentLocation();
  return { products, grades, locations, defaultLocation: locationId ?? (locations.length === 1 ? locations[0]!.id : "") };
}

const orNull = (s: string) => (s === "" ? null : s);

function itemBody(item: ItemValue) {
  return { product_id: item.productId, variety_id: orNull(item.varietyId), grade_id: orNull(item.gradeId) };
}

/* ---- receive / opening stock ------------------------------------------------------------------------ */

export function OpeningSheet({ onClose }: Props) {
  const { t } = useTranslation();
  const data = useFormData();
  const record = useRecordOpening();
  const [location, setLocation] = useState(data.defaultLocation);
  const [item, setItem] = useState<ItemValue>(EMPTY_ITEM);
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");

  if (!data.products.data || !data.grades.data) return <Sheet title={t("stock.receive")} onClose={onClose}><Loading /></Sheet>;
  const product = findProduct(data.products.data, item.productId);
  const quantity = product ? parseQuantity(qty, product.kind) : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!quantity || quantity < 1) return;
    record.mutate({ location_id: location, ...itemBody(item), quantity, note: note || null }, { onSuccess: onClose });
  }

  return (
    <Sheet title={t("stock.receive")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <LocationSelect label={t("stock.location")} value={location} onChange={setLocation} locations={data.locations} />
        <ItemFields value={item} onChange={setItem} products={data.products.data} grades={data.grades.data} />
        <QuantityField kind={product?.kind} value={qty} onChange={setQty} />
        <Field label={t("stock.note")}>
          <Input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={record.error} />
        <Button type="submit" disabled={record.isPending || !location || !quantity}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- adjust (add or remove, with a reason) ---------------------------------------------------------- */

export function AdjustSheet({ onClose }: Props) {
  const { t } = useTranslation();
  const data = useFormData();
  const adjust = useAdjustStock();
  const [location, setLocation] = useState(data.defaultLocation);
  const [item, setItem] = useState<ItemValue>(EMPTY_ITEM);
  const [direction, setDirection] = useState<"add" | "remove">("remove");
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("");

  if (!data.products.data || !data.grades.data) return <Sheet title={t("stock.adjust")} onClose={onClose}><Loading /></Sheet>;
  const product = findProduct(data.products.data, item.productId);
  const quantity = product ? parseQuantity(qty, product.kind) : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!quantity || quantity < 1) return;
    adjust.mutate(
      { location_id: location, ...itemBody(item), quantity: direction === "add" ? quantity : -quantity, reason },
      { onSuccess: onClose },
    );
  }

  return (
    <Sheet title={t("stock.adjust")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <LocationSelect label={t("stock.location")} value={location} onChange={setLocation} locations={data.locations} />
        <ItemFields value={item} onChange={setItem} products={data.products.data} grades={data.grades.data} />
        <div className="flex gap-2" role="radiogroup" aria-label={t("stock.direction")}>
          {(["remove", "add"] as const).map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={direction === d}
              onClick={() => setDirection(d)}
              className={`min-h-12 flex-1 rounded-xl border text-lg font-medium ${direction === d ? "border-violet-700 bg-violet-50 text-violet-700" : "border-slate-300"}`}
            >
              {t(`stock.direction_${d}`)}
            </button>
          ))}
        </div>
        <QuantityField kind={product?.kind} value={qty} onChange={setQty} />
        <Field label={t("stock.reason")} hint={t("stock.reasonHint")}>
          <Textarea required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={adjust.error} />
        <Button type="submit" disabled={adjust.isPending || !location || !quantity || reason.trim().length < 3}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- transfer between locations --------------------------------------------------------------------- */

type Line = { item: ItemValue; qty: string };

export function TransferSheet({ onClose }: Props) {
  const { t } = useTranslation();
  const data = useFormData();
  const transfer = useTransferStock();
  const [from, setFrom] = useState(data.defaultLocation);
  const [to, setTo] = useState("");
  const [lines, setLines] = useState<Line[]>([{ item: EMPTY_ITEM, qty: "" }]);
  const [note, setNote] = useState("");

  if (!data.products.data || !data.grades.data) return <Sheet title={t("stock.transfer")} onClose={onClose}><Loading /></Sheet>;
  const products = data.products.data;
  const grades = data.grades.data;

  const parsed = lines.map((l) => {
    const p = findProduct(products, l.item.productId);
    return { line: l, quantity: p ? parseQuantity(l.qty, p.kind) : null, kind: p?.kind };
  });
  const ready = from !== "" && to !== "" && from !== to && parsed.every((p) => p.quantity !== null && p.quantity > 0);

  function setLine(i: number, next: Partial<Line>) {
    setLines((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...next } : l)));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    transfer.mutate(
      {
        from_location_id: from,
        to_location_id: to,
        note: note || null,
        lines: parsed.map((p) => ({ ...itemBody(p.line.item), quantity: p.quantity! })),
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Sheet title={t("stock.transfer")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <LocationSelect label={t("stock.from")} value={from} onChange={setFrom} locations={data.locations} />
        <LocationSelect label={t("stock.to")} value={to} onChange={setTo} locations={data.locations.filter((l) => l.id !== from)} />
        {parsed.map((p, i) => (
          <div key={i} className="space-y-3 rounded-2xl bg-slate-50 p-3">
            <ItemFields value={p.line.item} onChange={(item) => setLine(i, { item })} products={products} grades={grades} />
            <QuantityField kind={p.kind} value={p.line.qty} onChange={(qty) => setLine(i, { qty })} />
            {lines.length > 1 && (
              <LinkButton type="button" onClick={() => setLines((prev) => prev.filter((_, idx) => idx !== i))}>
                {t("common.remove")}
              </LinkButton>
            )}
          </div>
        ))}
        <SecondaryButton type="button" className="w-full" onClick={() => setLines((prev) => [...prev, { item: EMPTY_ITEM, qty: "" }])}>
          + {t("stock.addLine")}
        </SecondaryButton>
        <Field label={t("stock.note")}>
          <Input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={transfer.error} />
        <Button type="submit" disabled={transfer.isPending || !ready}>
          {t("stock.transferNow")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- wastage ---------------------------------------------------------------------------------------- */

const REASONS: Schemas["WastageIn"]["reason_code"][] = ["rotten", "damaged", "shrinkage", "spoiled_in_transit", "other"];

export function WastageSheet({ onClose }: Props) {
  const { t } = useTranslation();
  const data = useFormData();
  const record = useRecordWastage();
  const [location, setLocation] = useState(data.defaultLocation);
  const [item, setItem] = useState<ItemValue>(EMPTY_ITEM);
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState<Schemas["WastageIn"]["reason_code"]>("rotten");
  const [note, setNote] = useState("");

  if (!data.products.data || !data.grades.data) return <Sheet title={t("wastage.record")} onClose={onClose}><Loading /></Sheet>;
  const product = findProduct(data.products.data, item.productId);
  const quantity = product ? parseQuantity(qty, product.kind) : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!quantity || quantity < 1) return;
    record.mutate(
      { location_id: location, ...itemBody(item), quantity, reason_code: reason, note: note || null },
      { onSuccess: onClose },
    );
  }

  return (
    <Sheet title={t("wastage.record")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <LocationSelect label={t("stock.location")} value={location} onChange={setLocation} locations={data.locations} />
        <ItemFields value={item} onChange={setItem} products={data.products.data} grades={data.grades.data} />
        <QuantityField kind={product?.kind} value={qty} onChange={setQty} />
        <Field label={t("wastage.reason")}>
          <Select value={reason} onChange={(e) => setReason(e.target.value as typeof reason)}>
            {REASONS.map((r) => (
              <option key={r} value={r}>
                {t(`wastage.reasons.${r}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("stock.note")}>
          <Input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={record.error} />
        <Button type="submit" disabled={record.isPending || !location || !quantity}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

/* ---- reverse a movement ----------------------------------------------------------------------------- */

export function ReverseSheet({ movementId, onClose }: { movementId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const reverse = useReverseMovement();
  const [reason, setReason] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    reverse.mutate({ movementId, reason }, { onSuccess: onClose });
  }

  return (
    <Sheet title={t("stock.reverse")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-slate-600">{t("stock.reverseHint")}</p>
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
