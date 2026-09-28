import { useTranslation } from "react-i18next";

/** Who owes whom: "they owe me" is a positive party-ledger amount, "I owe them" is negative. */
export function BalanceDirection({ value, onChange }: { value: "they" | "you"; onChange: (v: "they" | "you") => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex gap-2" role="radiogroup" aria-label={t("parties.direction")}>
      {(["they", "you"] as const).map((d) => (
        <button
          key={d}
          type="button"
          role="radio"
          aria-checked={value === d}
          onClick={() => onChange(d)}
          className={`min-h-12 flex-1 rounded-xl border text-base font-medium ${value === d ? "border-violet-700 bg-violet-50 text-violet-700" : "border-slate-300"}`}
        >
          {d === "they" ? t("parties.theyOweMe") : t("parties.iOweThem")}
        </button>
      ))}
    </div>
  );
}
