import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "../api/client";
import { useHome } from "../api/hooks";
import { formatMoney } from "../lib/format";
import { Card, ErrorText, Loading, StatTile } from "../lib/ui";
import { useName } from "../lib/useName";

type Action = { to: string; icon: string; label: string; needs?: string };

export function HomePage({ me, context }: { me: Schemas["MeOut"]; context: Schemas["WorkspaceContextOut"] }) {
  const { t } = useTranslation();
  const name = useName();
  const home = useHome();
  const can = (perm?: string) => perm === undefined || context.permissions.includes(perm);
  const enabled = (m: string) => context.business.enabled_modules.includes(m);

  const actions: (Action & { module: string })[] = [
    { module: "sell", to: "/w/sell", icon: "🛒", label: t("home.actions.sell"), needs: "bills.create" },
    { module: "buy", to: "/w/buy", icon: "🚚", label: t("home.actions.buy"), needs: "purchases.create" },
    { module: "money", to: "/w/money", icon: "💰", label: t("home.actions.money"), needs: "money.record" },
    { module: "stock", to: "/w/stock/opening", icon: "📥", label: t("home.actions.receive"), needs: "stock.move" },
    { module: "stock", to: "/w/stock/transfers?new=1", icon: "🔀", label: t("home.actions.transfer"), needs: "stock.move" },
    { module: "wastage", to: "/w/wastage", icon: "🗑️", label: t("home.actions.wastage"), needs: "stock.move" },
    { module: "customers", to: "/w/customers", icon: "👥", label: t("home.actions.customer"), needs: "parties.view" },
    { module: "suppliers", to: "/w/suppliers", icon: "🏭", label: t("home.actions.supplier"), needs: "parties.view" },
    { module: "stock", to: "/w/stock/products", icon: "🍌", label: t("home.actions.products"), needs: "catalog.view" },
  ];
  const visible = actions.filter((a) => enabled(a.module) && can(a.needs));

  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">{t("home.hello", { name: name(me) })} 👋</h1>
        <p className="text-lg text-slate-500">{t("home.howIsBusiness")}</p>
      </div>

      {home.isPending ? (
        <Loading />
      ) : home.error ? (
        <ErrorText error={home.error} />
      ) : (
        <HomeNumbers home={home.data} />
      )}

      {visible.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xl font-bold">{t("home.whatToDo")}</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {visible.map((a) => (
              <Link
                key={a.to + a.label}
                to={a.to}
                className="flex min-h-24 flex-col items-center justify-center gap-1 rounded-2xl border border-slate-200 bg-white p-3 text-center font-semibold shadow-sm active:bg-violet-50"
              >
                <span className="text-3xl" aria-hidden="true">
                  {a.icon}
                </span>
                {a.label}
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function HomeNumbers({ home }: { home: Schemas["HomeOut"] }) {
  const { t } = useTranslation();
  const name = useName();
  const top = home.top_owing_customers[0];
  const tiles: { key: string; label: string; value: string; tone: "good" | "warn" | "bad" | "neutral" | "brand"; hint?: string }[] = [];
  if (home.today_sales_paise !== null) {
    tiles.push({ key: "sales", label: t("home.todaySales"), value: formatMoney(home.today_sales_paise), tone: "good", hint: t("money.bills", { count: home.today_bills ?? 0 }) });
  }
  if (home.stock_items !== null) {
    tiles.push({ key: "stock", label: t("home.stockItems"), value: String(home.stock_items), tone: "neutral", hint: t("home.stockItemsHint") });
  }
  if (home.receivable_paise !== null) {
    tiles.push({ key: "recv", label: t("home.customerPending"), value: formatMoney(home.receivable_paise), tone: "warn" });
  }
  if (home.payable_paise !== null) {
    tiles.push({ key: "pay", label: t("home.supplierPending"), value: formatMoney(home.payable_paise), tone: "bad" });
  }
  if (home.crates_outstanding !== null) {
    tiles.push({ key: "crates", label: t("home.cratesOut"), value: String(home.crates_outstanding), tone: "brand", hint: t("home.cratesOutHint") });
  }
  return (
    <>
      {tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {tiles.map((tile) => (
            <StatTile key={tile.key} label={tile.label} value={tile.value} tone={tile.tone} hint={tile.hint} />
          ))}
        </div>
      )}
      {top && (
        <Card className="border-amber-200 bg-amber-50">
          <p className="text-lg">
            ⚠️ {t("home.owes", { name: name(top), amount: formatMoney(top.balance_paise) })}
          </p>
        </Card>
      )}
      {home.negative_stock_items !== null && home.negative_stock_items > 0 && (
        <Card className="border-rose-200 bg-rose-50">
          <p className="text-lg">⚠️ {t("home.negativeStock", { count: home.negative_stock_items })}</p>
        </Card>
      )}
    </>
  );
}
