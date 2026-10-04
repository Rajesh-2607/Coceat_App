import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useLogin } from "../api/hooks";
import { Button, ErrorText, Field, Input } from "../lib/ui";

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    login.mutate(
      { username: username.trim().toLowerCase(), password },
      { onSuccess: (me) => navigate(me.is_platform_admin && me.memberships.length === 0 ? "/admin" : "/w") },
    );
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-bold text-violet-700">{t("app.name")}</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label={t("login.username")}>
          <Input
            autoCapitalize="none"
            autoComplete="username"
            autoFocus
            maxLength={40}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </Field>
        <Field label={t("login.password")}>
          <Input
            type="password"
            autoComplete="current-password"
            maxLength={200}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <ErrorText error={login.error} />
        <Button type="submit" disabled={login.isPending || !username.trim() || !password}>
          {t("login.signIn")}
        </Button>
      </form>
    </main>
  );
}
