import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useRequestOtp, useVerifyOtp } from "../api/hooks";
import { Button, ErrorText, Field, Input, SecondaryButton } from "../lib/ui";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const requestOtp = useRequestOtp();
  const verifyOtp = useVerifyOtp();
  const challenge = requestOtp.data;

  function onRequest(e: FormEvent) {
    e.preventDefault();
    requestOtp.mutate(phone);
  }

  function onVerify(e: FormEvent) {
    e.preventDefault();
    if (!challenge) return;
    verifyOtp.mutate(
      { challenge_id: challenge.challenge_id, code },
      { onSuccess: (me) => navigate(me.is_platform_admin && me.memberships.length === 0 ? "/admin" : "/w") },
    );
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-bold text-green-800">{t("app.name")}</h1>
      {!challenge ? (
        <form onSubmit={onRequest} className="space-y-4">
          <Field label={t("login.phone")}>
            <Input
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              maxLength={14}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </Field>
          <ErrorText error={requestOtp.error} />
          <Button type="submit" disabled={requestOtp.isPending}>
            {t("login.sendOtp")}
          </Button>
        </form>
      ) : (
        <form onSubmit={onVerify} className="space-y-4">
          <p className="text-slate-600">{t("login.sentTo", { phone })}</p>
          <Field label={t("login.otp")}>
            <Input
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              required
              autoFocus
            />
          </Field>
          <ErrorText error={verifyOtp.error} />
          <Button type="submit" disabled={verifyOtp.isPending || code.length !== 6}>
            {t("login.verify")}
          </Button>
          <SecondaryButton
            type="button"
            className="w-full"
            onClick={() => {
              requestOtp.reset();
              verifyOtp.reset();
              setCode("");
            }}
          >
            {t("login.changeNumber")}
          </SecondaryButton>
        </form>
      )}
    </main>
  );
}
