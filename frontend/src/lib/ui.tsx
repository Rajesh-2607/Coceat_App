import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";
import { ApiError } from "../api/client";

/* ---- buttons -------------------------------------------------------------------------------------- */

export function Button({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`min-h-12 w-full rounded-xl bg-violet-700 px-4 text-lg font-semibold text-white active:bg-violet-800 disabled:opacity-50 ${className}`}
      {...props}
    />
  );
}

export function SecondaryButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`min-h-12 rounded-xl border border-slate-300 bg-white px-4 text-base font-medium active:bg-slate-100 disabled:opacity-50 ${className}`}
      {...props}
    />
  );
}

/** Small inline action (edit, deactivate, reverse). Still a 44px touch target. */
export function LinkButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`min-h-11 rounded-lg px-3 text-base font-medium text-violet-700 active:bg-violet-50 disabled:opacity-50 ${className}`}
      {...props}
    />
  );
}

/* ---- form fields ---------------------------------------------------------------------------------- */

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-base font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="block text-sm text-slate-500">{hint}</span>}
    </label>
  );
}

const control =
  "min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-lg focus:border-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-200";

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${control} ${className}`} {...props} />;
}

export function Select({ className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`${control} ${className}`} {...props} />;
}

export function Textarea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${control} py-2 ${className}`} rows={2} {...props} />;
}

/* ---- layout pieces -------------------------------------------------------------------------------- */

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {subtitle && <p className="text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>{children}</div>;
}

type Tone = "neutral" | "good" | "warn" | "bad" | "brand";

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-slate-900",
  good: "text-emerald-600",
  warn: "text-amber-600",
  bad: "text-rose-600",
  brand: "text-violet-700",
};

const TONE_PILL: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  good: "bg-emerald-50 text-emerald-700",
  warn: "bg-amber-50 text-amber-700",
  bad: "bg-rose-50 text-rose-700",
  brand: "bg-violet-50 text-violet-700",
};

export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
  pill,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  /** A small tinted corner badge (e.g. "Live" / "Watch" / "Alert") — the admin console's stat-tile style. */
  pill?: { label: string; tone: Tone };
}) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">{label}</p>
        {pill && <Badge tone={pill.tone}>{pill.label}</Badge>}
      </div>
      <p className={`mt-1 text-3xl font-bold ${TONE_TEXT[tone]}`}>{value}</p>
      {hint && <p className="text-sm text-slate-500">{hint}</p>}
    </Card>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium ${TONE_PILL[tone]}`}>{children}</span>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-slate-500">{children}</p>;
}

/** Route-based tab bar (each tab is a real URL, so back/forward and reload keep the place). */
export function TabBar({ tabs }: { tabs: { to: string; label: string; end?: boolean }[] }) {
  return (
    <nav className="flex gap-2 overflow-x-auto pb-1">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            `flex min-h-11 shrink-0 items-center rounded-full px-4 text-base font-medium ${isActive ? "bg-violet-700 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200"}`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** Bottom-sheet on phones, centred dialog on larger screens. Forms live in here to keep flows short. */
export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-slate-900/40 md:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <div className="max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl md:rounded-3xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-xl font-bold">{title}</h2>
          <button type="button" onClick={onClose} className="min-h-11 rounded-lg px-3 text-base text-slate-600" aria-label={t("common.close")}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ---- states --------------------------------------------------------------------------------------- */

/** Translated message for any error thrown by the API layer. */
export function ErrorText({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = error instanceof ApiError ? error.code : "unknown";
  return (
    <p role="alert" className="rounded-lg bg-red-50 p-3 text-base text-red-800">
      {t(`errors.${code}`, { defaultValue: t("errors.unknown") })}
    </p>
  );
}

export function Loading() {
  const { t } = useTranslation();
  return <p className="p-6 text-center text-slate-500">{t("common.loading")}</p>;
}

/** Shows Loading / the error / children for a TanStack query result. */
export function QueryBoundary<T>({
  query,
  children,
}: {
  query: { isPending: boolean; error: unknown; data: T | undefined };
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorText error={query.error} />;
  return <>{children(query.data as T)}</>;
}
