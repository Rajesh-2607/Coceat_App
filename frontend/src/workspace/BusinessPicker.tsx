import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useSelectBusiness } from "../api/hooks";
import { ErrorText } from "../lib/ui";

export function BusinessPicker({ me }: { me: Schemas["MeOut"] }) {
  const { t, i18n } = useTranslation();
  const select = useSelectBusiness();
  if (me.memberships.length === 0) {
    return <p className="p-6 text-lg">{t("business.none")}</p>;
  }
  return (
    <main className="mx-auto max-w-sm space-y-4 p-6">
      <h1 className="text-2xl font-bold">{t("business.choose")}</h1>
      {me.memberships.map((m) => (
        <button
          key={m.business_id}
          disabled={select.isPending}
          onClick={() => select.mutate(m.business_id)}
          className="block min-h-14 w-full rounded-xl border border-slate-300 px-4 text-left text-lg font-medium active:bg-slate-100"
        >
          {(i18n.language === "ta" && m.business_name_ta) || m.business_name}
        </button>
      ))}
      <ErrorText error={select.error} />
    </main>
  );
}
