import { useTranslation } from "react-i18next";
import { MODULE_ORDER } from "../workspace/modules";

/** Toggle grid of workspace modules. Turning one off makes the API refuse it (403), not just hide it. */
export function ModulePicker({ value, onChange }: { value: string[]; onChange: (next: string[]) => void }) {
  const { t } = useTranslation();
  return (
    <fieldset className="space-y-2">
      <legend className="text-base font-medium text-slate-700">{t("admin.modules")}</legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {MODULE_ORDER.map((m) => {
          const on = value.includes(m);
          return (
            <label
              key={m}
              className={`flex min-h-16 cursor-pointer items-center justify-between gap-2 rounded-xl border p-3 ${
                on ? "border-violet-200 bg-violet-50" : "border-slate-200 bg-white"
              }`}
            >
              <span className="min-w-0">
                <span className="block font-medium">{t(`nav.${m}`)}</span>
                <span className="block truncate text-sm text-slate-500">{t(`admin.moduleDesc.${m}`)}</span>
              </span>
              <input
                type="checkbox"
                className="sr-only"
                checked={on}
                onChange={(e) => onChange(e.target.checked ? [...value, m] : value.filter((x) => x !== m))}
              />
              <span
                aria-hidden="true"
                className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${on ? "bg-violet-700" : "bg-slate-300"}`}
              >
                <span
                  className={`inline-block size-5 transform rounded-full bg-white transition-transform ${on ? "translate-x-5" : "translate-x-0.5"}`}
                />
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
