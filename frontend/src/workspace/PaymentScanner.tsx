import { useTranslation } from "react-i18next";

/** Shows the shop's UPI scanner for the customer to scan. Placeholder image until the real QR is added. */
export function PaymentScanner() {
  const { t } = useTranslation();
  return (
    <figure className="flex flex-col items-center gap-2 rounded-2xl border border-slate-200 bg-white p-4">
      <img src="/payment-scanner.svg" alt={t("pay.scanAlt")} className="size-48" />
      <figcaption className="text-center text-sm text-slate-500">{t("pay.scanHint")}</figcaption>
    </figure>
  );
}
