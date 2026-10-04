import { useTranslation } from "react-i18next";
import type { Schemas } from "../../api/client";
import { Field, Input, Select } from "../../lib/ui";
import { useName } from "../../lib/useName";

export type Product = Schemas["ProductOut"];

/** The (product, variety, grade) a stock line refers to. Empty string = not chosen / none. */
export type ItemValue = { productId: string; varietyId: string; gradeId: string };
export const EMPTY_ITEM: ItemValue = { productId: "", varietyId: "", gradeId: "" };

export function findProduct(products: Product[], id: string): Product | undefined {
  return products.find((p) => p.id === id);
}

/** Product, then that product's varieties, then grades: three short selects instead of one long list. */
export function ItemFields({
  value,
  onChange,
  products,
  grades,
}: {
  value: ItemValue;
  onChange: (next: ItemValue) => void;
  products: Product[];
  grades: Schemas["GradeOut"][];
}) {
  const { t } = useTranslation();
  const name = useName();
  const product = findProduct(products, value.productId);
  const varieties = (product?.varieties ?? []).filter((v) => v.is_active);
  const activeGrades = grades.filter((g) => g.is_active);
  return (
    <div className="space-y-3">
      <Field label={t("stock.product")}>
        <Select
          required
          value={value.productId}
          onChange={(e) => onChange({ productId: e.target.value, varietyId: "", gradeId: value.gradeId })}
        >
          <option value="">{t("common.choose")}</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {name(p)}
            </option>
          ))}
        </Select>
      </Field>
      {varieties.length > 0 && (
        <Field label={t("stock.variety")}>
          <Select value={value.varietyId} onChange={(e) => onChange({ ...value, varietyId: e.target.value })}>
            <option value="">{t("common.none")}</option>
            {varieties.map((v) => (
              <option key={v.id} value={v.id}>
                {name(v)}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {activeGrades.length > 0 && (
        <Field label={t("stock.grade")}>
          <Select value={value.gradeId} onChange={(e) => onChange({ ...value, gradeId: e.target.value })}>
            <option value="">{t("common.none")}</option>
            {activeGrades.map((g) => (
              <option key={g.id} value={g.id}>
                {name(g)}
              </option>
            ))}
          </Select>
        </Field>
      )}
    </div>
  );
}

/** Quantity typed in kg for weight products and whole pieces for count products. */
export function QuantityField({
  kind,
  value,
  onChange,
  label,
}: {
  kind: Schemas["ProductOut"]["kind"] | undefined;
  value: string;
  onChange: (v: string) => void;
  label?: string;
}) {
  const { t } = useTranslation();
  const isWeight = kind !== "count";
  return (
    <Field label={`${label ?? t("stock.quantity")} (${isWeight ? t("units.kg") : t("units.pcs")})`}>
      <Input
        required
        inputMode="decimal"
        autoComplete="off"
        placeholder={isWeight ? "0.0" : "0"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

export function LocationSelect({
  label,
  value,
  onChange,
  locations,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  locations: Schemas["LocationOut"][];
}) {
  const { t } = useTranslation();
  const name = useName();
  return (
    <Field label={label}>
      <Select required value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("common.choose")}</option>
        {locations.map((l) => (
          <option key={l.id} value={l.id}>
            {name(l)}
          </option>
        ))}
      </Select>
    </Field>
  );
}
