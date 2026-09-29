import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAdminBusinesses, useAdminSubscriptionStats } from "../api/hooks";
import { formatDateTime } from "../lib/format";
import { Badge, Button, Card, EmptyState, PageHeader, QueryBoundary, SecondaryButton, StatTile } from "../lib/ui";
import { useName } from "../lib/useName";

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const name = useName();
  const businesses = useAdminBusinesses();
  const subStats = useAdminSubscriptionStats();
  return (
    <section className="space-y-5">
      <QueryBoundary query={businesses}>
        {(rows) => {
          const active = rows.filter((b) => b.status === "active").length;
          const pendingSetup = rows.filter((b) => b.setup_completed_at === null).length;
          const recent = rows.slice(0, 5);
          const mostRecent = rows[0];
          const quarterStart = new Date();
          quarterStart.setMonth(Math.floor(quarterStart.getMonth() / 3) * 3, 1);
          quarterStart.setHours(0, 0, 0, 0);
          const newThisQuarter = rows.filter((b) => new Date(b.created_at) >= quarterStart).length;
          return (
            <>
              <PageHeader
                title={t("admin.platform")}
                subtitle={t("admin.platformHint")}
                actions={
                  <>
                    <Link to="/admin/businesses">
                      <SecondaryButton type="button">{t("admin.allBusinesses")}</SecondaryButton>
                    </Link>
                    {mostRecent && (
                      <Link to={`/admin/businesses/${mostRecent.id}`}>
                        <Button type="button" className="!w-auto">
                          {t("admin.configureBusiness", { name: name(mostRecent) })}
                        </Button>
                      </Link>
                    )}
                  </>
                }
              />
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <StatTile label={t("admin.totalBusinesses")} value={rows.length} hint={t("admin.thisQuarter", { count: newThisQuarter })} pill={{ label: t("admin.pillLive"), tone: "brand" }} />
                <StatTile
                  label={t("admin.active")}
                  value={active}
                  hint={rows.length ? t("admin.percentOfAccounts", { pct: Math.round((active / rows.length) * 100) }) : undefined}
                  pill={{ label: t("admin.pillLive"), tone: "good" }}
                />
                <Link to="/admin/subscriptions" className="block">
                  <QueryBoundary query={subStats}>
                    {(s) => <StatTile label={t("admin.subStatus.trial")} value={s.trial} hint={t("admin.expiringSoonHint", { count: s.expiring_soon })} pill={{ label: t("admin.pillWatch"), tone: "warn" }} />}
                  </QueryBoundary>
                </Link>
                <Link to="/admin/businesses" className="block">
                  <StatTile label={t("admin.setupPending")} value={pendingSetup} hint={t("admin.awaitingConfiguration")} pill={{ label: t("admin.pillAlert"), tone: pendingSetup > 0 ? "bad" : "neutral" }} />
                </Link>
              </div>
              <Card className="space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold">{t("admin.recent")}</h2>
                    <p className="text-sm text-slate-500">{t("admin.recentHint")}</p>
                  </div>
                  <Link to="/admin/businesses" className="flex min-h-11 items-center font-medium text-violet-700">
                    {t("admin.viewAll")} →
                  </Link>
                </div>
                {recent.length === 0 ? (
                  <EmptyState>{t("admin.noBusinesses")}</EmptyState>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-left text-sm">
                      <thead>
                        <tr className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          <th className="px-2 py-2">{t("admin.colBusiness")}</th>
                          <th className="px-2 py-2">{t("admin.colType")}</th>
                          <th className="px-2 py-2">{t("admin.colLocations")}</th>
                          <th className="px-2 py-2">{t("admin.colModules")}</th>
                          <th className="px-2 py-2">{t("admin.colStatus")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recent.map((b) => (
                          <tr key={b.id} className="border-t border-slate-100">
                            <td className="px-2 py-3">
                              <Link to={`/admin/businesses/${b.id}`} className="font-semibold text-violet-700">
                                {name(b)}
                              </Link>
                              <p className="text-xs text-slate-400">{formatDateTime(b.created_at, i18n.language)}</p>
                            </td>
                            <td className="px-2 py-3 text-slate-500">{b.vertical_key}</td>
                            <td className="px-2 py-3">{b.location_count}</td>
                            <td className="px-2 py-3">{b.enabled_modules.length}</td>
                            <td className="px-2 py-3">
                              <Badge tone={b.status === "active" ? "good" : "bad"}>{t(`admin.status.${b.status}`)}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </>
          );
        }}
      </QueryBoundary>
    </section>
  );
}
