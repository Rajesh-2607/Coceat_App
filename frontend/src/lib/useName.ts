import { useTranslation } from "react-i18next";

/** Pick the Tamil name when the UI is in Tamil and one exists, else the English name. */
export function useName() {
  const { i18n } = useTranslation();
  return <T extends { name: string; name_ta?: string | null }>(item: T): string =>
    (i18n.language === "ta" && item.name_ta) || item.name;
}

/** Quantity unit labels for formatQuantity, in the current language. */
export function useQuantityLabels() {
  const { t } = useTranslation();
  return { kg: t("units.kg"), g: t("units.g"), pcs: t("units.pcs") };
}
