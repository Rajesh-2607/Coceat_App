import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import type { Schemas } from "../api/client";
import { useLogout, useWorkspaceContext } from "../api/hooks";
import { Badge, ErrorText, Loading, Select } from "../lib/ui";
import { useName } from "../lib/useName";
import { AuditPage } from "./AuditPage";
import { BillDetailPage } from "./bills/BillDetailPage";
import { BillsPage } from "./bills/BillsPage";
import { BuyPage, PurchaseDetailPage } from "./buy/BuyPage";
import { BusinessPicker } from "./BusinessPicker";
import { ComingSoon } from "./ComingSoon";
import { HomePage } from "./HomePage";
import { LocationProvider, useCurrentLocation } from "./location";
import { BUILT_MODULES, visibleModules, type ModuleKey } from "./modules";
import { MoneyPage } from "./money/MoneyPage";
import { PartiesPage } from "./parties/PartiesPage";
import { PartyDetailPage } from "./parties/PartyDetailPage";
import { ReportsPage } from "./reports/ReportsPage";
import { SellPage } from "./sell/SellPage";
import { SettingsPage } from "./SettingsPage";
import { StaffPage } from "./StaffPage";
import { StockPage } from "./stock/StockPage";
import { WastagePage } from "./WastagePage";

export function WorkspaceApp({ me }: { me: Schemas["MeOut"] }) {
  const hasBusiness = me.current_business_id !== null;
  const context = useWorkspaceContext(hasBusiness);
  if (!hasBusiness) return <BusinessPicker me={me} />;
  if (context.isPending) return <Loading />;
  if (context.error) return <ErrorText error={context.error} />;
  return (
    <LocationProvider businessId={context.data.business.id}>
      <Shell me={me} context={context.data} />
    </LocationProvider>
  );
}

const ICONS: Record<ModuleKey | "home", string> = {
  home: "🏠",
  sell: "🛒",
  stock: "📦",
  money: "💰",
  buy: "🚚",
  bills: "🧾",
  customers: "👥",
  suppliers: "🏭",
  wastage: "🗑️",
  reports: "📊",
  staff: "🧑‍💼",
  audit: "📜",
  settings: "⚙️",
};

function Shell({ me, context }: { me: Schemas["MeOut"]; context: Schemas["WorkspaceContextOut"] }) {
  const { t, i18n } = useTranslation();
  const name = useName();
  const navigate = useNavigate();
  const logout = useLogout();
  const [menuOpen, setMenuOpen] = useState(false);
  const { locationId, setLocationId, locations } = useCurrentLocation();
  const modules = visibleModules(context.business.enabled_modules, context.permissions);

  const nav = (
    <nav className="flex flex-col gap-1" aria-label={t("nav.menu")}>
      <NavItem to="/w" end module="home" label={t("nav.home")} onClick={() => setMenuOpen(false)} />
      {modules.map((m) => (
        <NavItem key={m} to={`/w/${m}`} module={m} label={t(`nav.${m}`)} onClick={() => setMenuOpen(false)} />
      ))}
    </nav>
  );

  return (
    <div className="min-h-dvh bg-slate-50 md:flex">
      <aside className="hidden w-64 shrink-0 flex-col gap-4 border-r border-slate-200 bg-white p-3 md:flex">
        <BusinessTitle context={context} />
        {nav}
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-30 md:hidden" role="dialog" aria-modal="true">
          <button className="absolute inset-0 bg-slate-900/40" aria-label={t("common.close")} onClick={() => setMenuOpen(false)} />
          <aside className="relative flex h-full w-72 max-w-[85%] flex-col gap-4 overflow-y-auto bg-white p-3 shadow-xl">
            <BusinessTitle context={context} />
            {nav}
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
          <button
            className="min-h-11 min-w-11 rounded-xl border border-slate-200 text-xl md:hidden"
            aria-label={t("nav.menu")}
            onClick={() => setMenuOpen(true)}
          >
            ☰
          </button>
          {locations.length > 0 && (
            <Select
              className="!min-h-11 max-w-56 !text-base"
              aria-label={t("location.switch")}
              value={locationId ?? ""}
              onChange={(e) => setLocationId(e.target.value || null)}
            >
              <option value="">{t("location.all")}</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {name(l)}
                </option>
              ))}
            </Select>
          )}
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden sm:inline">
              <Badge>{t(`roles.${context.role}`, { defaultValue: context.role })}</Badge>
            </span>
            <button
              className="min-h-11 rounded-full bg-violet-700 px-4 text-base font-semibold text-white"
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
          </div>
        </header>

        <main className="mx-auto max-w-5xl space-y-5 p-4 md:p-6">
          <Routes>
            <Route index element={<HomePage me={me} context={context} />} />
            {modules.includes("sell") && <Route path="sell" element={<SellPage context={context} />} />}
            {modules.includes("bills") && (
              <>
                <Route path="bills" element={<BillsPage />} />
                <Route path="bills/:id" element={<BillDetailPage context={context} />} />
              </>
            )}
            {modules.includes("money") && <Route path="money" element={<MoneyPage context={context} />} />}
            {modules.includes("buy") && (
              <>
                <Route path="buy" element={<BuyPage context={context} />} />
                <Route path="buy/:id" element={<PurchaseDetailPage context={context} />} />
              </>
            )}
            {modules.includes("reports") && <Route path="reports" element={<ReportsPage />} />}
            {modules.includes("stock") && <Route path="stock/*" element={<StockPage context={context} />} />}
            {modules.includes("customers") && (
              <>
                <Route path="customers" element={<PartiesPage kind="customers" context={context} />} />
                <Route path="customers/:id" element={<PartyDetailPage kind="customers" context={context} />} />
              </>
            )}
            {modules.includes("suppliers") && (
              <>
                <Route path="suppliers" element={<PartiesPage kind="suppliers" context={context} />} />
                <Route path="suppliers/:id" element={<PartyDetailPage kind="suppliers" context={context} />} />
              </>
            )}
            {modules.includes("wastage") && <Route path="wastage" element={<WastagePage context={context} />} />}
            {modules.includes("staff") && <Route path="staff" element={<StaffPage context={context} meId={me.id} />} />}
            {modules.includes("audit") && <Route path="audit" element={<AuditPage />} />}
            {modules.includes("settings") && <Route path="settings" element={<SettingsPage context={context} />} />}
            {modules
              .filter((m) => !BUILT_MODULES.has(m))
              .map((m) => (
                <Route key={m} path={`${m}/*`} element={<ComingSoon module={m} />} />
              ))}
            <Route path="*" element={<ComingSoon />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function BusinessTitle({ context }: { context: Schemas["WorkspaceContextOut"] }) {
  const name = useName();
  return (
    <div className="px-2 pt-1">
      <p className="text-xs font-bold uppercase tracking-widest text-violet-700">Cocreat</p>
      <p className="truncate text-lg font-bold">{name(context.business)}</p>
    </div>
  );
}

function NavItem({
  to,
  label,
  module,
  end,
  onClick,
}: {
  to: string;
  label: string;
  module: ModuleKey | "home";
  end?: boolean;
  onClick: () => void;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        `flex min-h-12 items-center gap-3 rounded-xl px-3 text-base font-medium ${isActive ? "bg-violet-50 text-violet-700" : "text-slate-700 active:bg-slate-100"}`
      }
    >
      <span aria-hidden="true" className="w-6 text-center text-lg">
        {ICONS[module]}
      </span>
      {label}
    </NavLink>
  );
}
