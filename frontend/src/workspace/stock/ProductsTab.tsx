import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../../api/client";
import { useAddVariety, useCreateProduct, useProducts, useUnits, useUpdateProduct } from "../../api/hooks";
import { formatMoney, paiseToInput, parseRupees } from "../../lib/format";
import { Badge, Button, Card, EmptyState, ErrorText, Field, Input, LinkButton, QueryBoundary, Select, Sheet } from "../../lib/ui";
import { useName } from "../../lib/useName";

type Product = Schemas["ProductOut"];
const GST_RATES = [0, 25, 300, 500, 1200, 1800, 2800];

export function ProductsTab({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const name = useName();
  const [showInactive, setShowInactive] = useState(false);
  const products = useProducts(showInactive);
  const units = useUnits();
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [varietyFor, setVarietyFor] = useState<Product | null>(null);
  const unitOf = (id: string) => units.data?.find((u) => u.id === id);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {canManage && <Button className="!w-auto" onClick={() => setEditing("new")}>+ {t("catalog.addProduct")}</Button>}
        <label className="flex min-h-11 items-center gap-2 text-base text-slate-700">
          <input type="checkbox" className="size-5" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          {t("catalog.showInactive")}
        </label>
      </div>
      <QueryBoundary query={products}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("catalog.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((p) => {
                const unit = unitOf(p.unit_id);
                return (
                  <li key={p.id}>
                    <Card className="space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-lg font-semibold">{name(p)}</p>
                          <p className="text-sm text-slate-500">
                            {t(`catalog.kinds.${p.kind}`)}
                            {unit ? ` · ${name(unit)}` : ""}
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          {p.default_price_paise !== null && p.default_price_paise !== undefined ? (
                            <p className="text-lg font-bold">
                              {formatMoney(p.default_price_paise)}
                              <span className="text-sm font-normal text-slate-500"> / {unit ? unit.code : ""}</span>
                            </p>
                          ) : (
                            <p className="text-sm text-slate-400">{t("catalog.noPrice")}</p>
                          )}
                          {p.gst_rate_bp > 0 && <Badge tone="brand">GST {p.gst_rate_bp / 100}%</Badge>}
                          {!p.is_active && <Badge tone="warn">{t("common.inactive")}</Badge>}
                        </div>
                      </div>
                      {p.varieties.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {p.varieties.map((v) => (
                            <Badge key={v.id} tone={v.is_active ? "brand" : "neutral"}>
                              {name(v)}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {canManage && (
                        <div className="flex gap-1">
                          <LinkButton onClick={() => setEditing(p)}>{t("common.edit")}</LinkButton>
                          <LinkButton onClick={() => setVarietyFor(p)}>+ {t("catalog.addVariety")}</LinkButton>
                        </div>
                      )}
                    </Card>
                  </li>
                );
              })}
            </ul>
          )
        }
      </QueryBoundary>
      {editing && <ProductSheet product={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {varietyFor && <VarietySheet product={varietyFor} onClose={() => setVarietyFor(null)} />}
    </div>
  );
}

function ProductSheet({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const { t } = useTranslation();
  const name = useName();
  const units = useUnits();
  const create = useCreateProduct();
  const update = useUpdateProduct(product?.id ?? "");
  const [nameEn, setNameEn] = useState(product?.name ?? "");
  const [nameTa, setNameTa] = useState(product?.name_ta ?? "");
  const [kind, setKind] = useState<Product["kind"]>(product?.kind ?? "weight");
  const [unitId, setUnitId] = useState(product?.unit_id ?? "");
  const [price, setPrice] = useState(product?.default_price_paise != null ? paiseToInput(product.default_price_paise) : "");
  const [active, setActive] = useState(product?.is_active ?? true);
  const [gstRate, setGstRate] = useState(product?.gst_rate_bp ?? 0);
  const [hsn, setHsn] = useState(product?.hsn_code ?? "");
  const write = product ? update : create;

  const kindUnits = (units.data ?? []).filter((u) => u.kind === kind && u.is_active);
  const priceValue = price.trim() === "" ? null : parseRupees(price);
  const priceInvalid = price.trim() !== "" && priceValue === null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (priceInvalid) return;
    if (product) {
      update.mutate(
        {
          name: nameEn,
          name_ta: nameTa || null,
          unit_id: unitId,
          default_price_paise: priceValue,
          gst_rate_bp: gstRate,
          hsn_code: hsn || null,
          is_active: active,
        },
        { onSuccess: onClose },
      );
    } else {
      create.mutate(
        {
          name: nameEn,
          name_ta: nameTa || null,
          kind,
          unit_id: unitId,
          default_price_paise: priceValue,
          gst_rate_bp: gstRate,
          hsn_code: hsn || null,
        },
        { onSuccess: onClose },
      );
    }
  }

  return (
    <Sheet title={product ? t("catalog.editProduct") : t("catalog.addProduct")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("catalog.name")}>
          <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("catalog.nameTa")}>
          <Input maxLength={200} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        {!product && (
          <Field label={t("catalog.kind")}>
            <Select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Product["kind"]);
                setUnitId("");
              }}
            >
              <option value="weight">{t("catalog.kinds.weight")}</option>
              <option value="count">{t("catalog.kinds.count")}</option>
            </Select>
          </Field>
        )}
        <Field label={t("catalog.unit")}>
          <Select required value={unitId} onChange={(e) => setUnitId(e.target.value)}>
            <option value="">{t("common.choose")}</option>
            {kindUnits.map((u) => (
              <option key={u.id} value={u.id}>
                {name(u)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("catalog.price")} hint={t("catalog.priceHint")}>
          <Input inputMode="decimal" placeholder="0.00" value={price} onChange={(e) => setPrice(e.target.value)} aria-invalid={priceInvalid} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("catalog.gstRate")} hint={t("catalog.gstHint")}>
            <Select value={String(gstRate)} onChange={(e) => setGstRate(Number(e.target.value))}>
              {GST_RATES.map((r) => (
                <option key={r} value={r}>
                  {r / 100}%
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("catalog.hsn")}>
            <Input inputMode="numeric" maxLength={8} pattern="\d{4,8}" value={hsn} onChange={(e) => setHsn(e.target.value.replace(/\D/g, ""))} />
          </Field>
        </div>
        {product && (
          <label className="flex min-h-11 items-center gap-2 text-lg">
            <input type="checkbox" className="size-5" checked={active} onChange={(e) => setActive(e.target.checked)} />
            {t("common.active")}
          </label>
        )}
        <ErrorText error={write.error} />
        <Button type="submit" disabled={write.isPending || !unitId || priceInvalid}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}

function VarietySheet({ product, onClose }: { product: Product; onClose: () => void }) {
  const { t } = useTranslation();
  const name = useName();
  const add = useAddVariety(product.id);
  const [nameEn, setNameEn] = useState("");
  const [nameTa, setNameTa] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    add.mutate({ name: nameEn, name_ta: nameTa || null }, { onSuccess: onClose });
  }

  return (
    <Sheet title={`${t("catalog.addVariety")} — ${name(product)}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("catalog.name")}>
          <Input required maxLength={80} value={nameEn} onChange={(e) => setNameEn(e.target.value)} autoFocus />
        </Field>
        <Field label={t("catalog.nameTa")}>
          <Input maxLength={120} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <ErrorText error={add.error} />
        <Button type="submit" disabled={add.isPending}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
