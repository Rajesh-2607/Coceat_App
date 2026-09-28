import { useTranslation } from "react-i18next";
import { MODULE_ORDER } from "../workspace/modules";

/** Checklist of workspace modules. Turning one off makes the API refuse it (403), not just hide it. */
export function ModulePicker({ value, onChange }: { value: string[]; onChange: (next: string[]) => void }) {
  const { t } = useTranslation();
  return (
    <fieldset className="space-y-1">
      <legend className="text-base font-medium text-slate-700">{t("admin.modules")}</legend>
      <div className="grid grid-cols-2 gap-1">
        {MODULE_ORDER.map((m) => (
          <label key={m} className="flex min-h-11 items-center gap-2 text-base">
            <input
              type="checkbox"
              className="size-5"
              checked={value.includes(m)}
              onChange={(e) => onChange(e.target.checked ? [...value, m] : value.filter((x) => x !== m))}
            />
            {t(`nav.${m}`)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
