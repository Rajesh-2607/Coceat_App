import { useTranslation } from "react-i18next";
import { Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useLogout, useMe } from "../api/hooks";
import { BusinessDetailPage } from "./BusinessDetailPage";
import { BusinessesPage } from "./BusinessesPage";
import { ConfigurationPage } from "./ConfigurationPage";
import { OverviewPage } from "./OverviewPage";
import { SettingsPage } from "./SettingsPage";
import { SubscriptionsPage } from "./SubscriptionsPage";
import { UsersPage } from "./UsersPage";

/** Platform admin console: the Cocreat team manages businesses, their modules and their people. */
export function AdminApp() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const logout = useLogout();
  const me = useMe();
  const hasWorkspace = (me.data?.memberships.length ?? 0) > 0;

  return (
    <div className="min-h-dvh bg-slate-50 md:flex">
      <aside className="border-b border-slate-200 bg-white p-3 md:w-64 md:shrink-0 md:border-r md:border-b-0">
        <div className="px-2 pb-2 md:pb-4">
          <p className="text-xs font-bold uppercase tracking-widest text-violet-700">Cocreat</p>
          <p className="text-lg font-bold">{t("admin.title")}</p>
        </div>
        <nav className="flex gap-1 md:flex-col" aria-label={t("nav.menu")}>
          <AdminNavItem to="/admin" end icon="▦" label={t("admin.overview")} />
          <AdminNavItem to="/admin/businesses" icon="🏢" label={t("admin.businesses")} />
          <AdminNavItem to="/admin/subscriptions" icon="💳" label={t("admin.subscriptions")} />
          <AdminNavItem to="/admin/users" icon="👥" label={t("admin.users")} />
          <AdminNavItem to="/admin/configuration" icon="🌱" label={t("admin.configuration")} />
          <AdminNavItem to="/admin/settings" icon="⚙️" label={t("admin.settings")} />
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-center justify-end gap-2 border-b border-slate-200 bg-white px-4 py-2">
          {hasWorkspace && (
            <Link to="/w" className="flex min-h-11 items-center rounded-full bg-violet-700 px-4 font-semibold text-white">
              {t("admin.launchWorkspace")} ↗
            </Link>
          )}
          <button
            className="min-h-11 rounded-full px-4 text-base font-semibold text-violet-700 ring-1 ring-violet-200"
            onClick={() => void i18n.changeLanguage(i18n.language === "ta" ? "en" : "ta")}
          >
            {t("language.switch")}
          </button>
          <button
            className="min-h-11 rounded-lg px-3 text-base font-medium text-slate-700"
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            {t("common.logout")}
          </button>
        </header>
        <main className="mx-auto max-w-7xl space-y-5 p-4 md:p-6">
          <Routes>
            <Route index element={<OverviewPage />} />
            <Route path="businesses" element={<BusinessesPage />} />
            <Route path="businesses/:id" element={<BusinessDetailPage />} />
            <Route path="subscriptions" element={<SubscriptionsPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="configuration" element={<ConfigurationPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function AdminNavItem({ to, label, icon, end }: { to: string; label: string; icon: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex min-h-12 flex-1 items-center gap-3 rounded-xl px-3 text-base font-medium md:flex-none ${isActive ? "bg-violet-50 text-violet-700" : "text-slate-700 active:bg-slate-100"}`
      }
    >
      <span aria-hidden="true" className="w-6 text-center text-lg">
        {icon}
      </span>
      {label}
    </NavLink>
  );
}
