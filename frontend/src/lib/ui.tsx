import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";

export function Button({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`min-h-12 w-full rounded-xl bg-green-700 px-4 text-lg font-semibold text-white active:bg-green-800 disabled:opacity-50 ${className}`}
      {...props}
    />
  );
}

export function SecondaryButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`min-h-12 rounded-xl border border-slate-300 px-4 text-base font-medium active:bg-slate-100 ${className}`}
      {...props}
    />
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-base font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className="min-h-12 w-full rounded-xl border border-slate-300 px-3 text-lg focus:border-green-700 focus:outline-none"
      {...props}
    />
  );
}

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
