import { useTranslation } from "react-i18next";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import type { Schemas } from "../api/client";
import { useLogout, useWorkspaceContext } from "../api/hooks";
import { ErrorText, Loading } from "../lib/ui";
import { BusinessPicker } from "./BusinessPicker";
import { LocationsPage } from "./LocationsPage";
import { visibleModules } from "./modules";

export function WorkspaceApp({ me }: { me: Schemas["MeOut"] }) {
  const hasBusiness = me.current_business_id !== null;
  const context = useWorkspaceContext(hasBusiness);
  if (!hasBusiness) return <BusinessPicker me={me} />;
  if (context.isPending) return <Loading />;
  if (context.error) return <ErrorText error={context.error} />;
  return <Shell me={me} context={context.data} />;
}

function Shell({ me, context }: { me: Schemas["MeOut"]; context: Schemas["WorkspaceContextOut"] }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const logout = useLogout();
  const modules = visibleModules(context.business.enabled_modules);
  const business = (i18n.language === "ta" && context.business.name_ta) || context.business.name;

  return (
    <div className="mx-auto flex min-h-dvh max-w-3xl flex-col">
      <header className="flex items-center justify-between gap-2 border-b px-4 py-3">
        <strong className="truncate text-lg text-green-800">{business}</strong>
        <div className="flex gap-2">
          <button
            className="min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700"
            onClick={() => void i18n.changeLanguage(i18n.language === "ta" ? "en" : "ta")}
          >
            {t("language.switch")}
          </button>
          <button
            className="min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700"
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            {t("common.logout")}
          </button>
        </div>
      </header>

      <nav className="flex gap-2 overflow-x-auto border-b px-4 py-2">
        <NavItem to="/w" end label={t("nav.home")} />
        {modules.map((m) => (
          <NavItem key={m} to={`/w/${m}`} label={t(`nav.${m}`)} />
        ))}
      </nav>

      <main className="flex-1 p-4">
        <Routes>
          <Route index element={<h1 className="text-2xl font-bold">{t("home.welcome", { name: me.name })}</h1>} />
          {modules.includes("stock") && (
            <Route
              path="stock"
              element={<LocationsPage canManage={context.permissions.includes("locations.manage")} />}
            />
          )}
          <Route path="*" element={<p className="text-slate-500">{t("home.comingSoon")}</p>} />
        </Routes>
      </main>
    </div>
  );
}

function NavItem({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex min-h-11 shrink-0 items-center rounded-full px-4 text-base ${isActive ? "bg-green-700 text-white" : "bg-slate-100"}`
      }
    >
      {label}
    </NavLink>
  );
}
