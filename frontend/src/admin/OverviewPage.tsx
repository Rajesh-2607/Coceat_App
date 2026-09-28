import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAdminBusinesses } from "../api/hooks";
import { formatDateTime } from "../lib/format";
import { Badge, Card, EmptyState, PageHeader, QueryBoundary, StatTile } from "../lib/ui";
import { useName } from "../lib/useName";

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const name = useName();
  const businesses = useAdminBusinesses();
  return (
    <section className="space-y-5">
      <PageHeader title={t("admin.platform")} subtitle={t("admin.platformHint")} />
      <QueryBoundary query={businesses}>
        {(rows) => {
          const active = rows.filter((b) => b.status === "active").length;
          const recent = rows.slice(0, 5);
          return (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatTile label={t("admin.totalBusinesses")} value={rows.length} tone="brand" />
                <StatTile
                  label={t("admin.active")}
                  value={active}
                  tone="good"
                  hint={rows.length ? `${Math.round((active / rows.length) * 100)}%` : undefined}
                />
                <StatTile label={t("admin.suspended")} value={rows.length - active} tone={rows.length - active > 0 ? "bad" : "neutral"} />
                <StatTile label={t("admin.verticalsInUse")} value={new Set(rows.map((b) => b.vertical_key)).size} />
              </div>
              <Card className="space-y-2">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold">{t("admin.recent")}</h2>
                  <Link to="/admin/businesses" className="flex min-h-11 items-center font-medium text-violet-700">
                    {t("admin.viewAll")} →
                  </Link>
                </div>
                {recent.length === 0 ? (
                  <EmptyState>{t("admin.noBusinesses")}</EmptyState>
                ) : (
                  <ul className="divide-y">
                    {recent.map((b) => (
                      <li key={b.id}>
                        <Link to={`/admin/businesses/${b.id}`} className="flex min-h-14 items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-lg font-semibold">{name(b)}</p>
                            <p className="text-sm text-slate-500">
                              {b.vertical_key} · {formatDateTime(b.created_at, i18n.language)}
                            </p>
                          </div>
                          <Badge tone={b.status === "active" ? "good" : "bad"}>{t(`admin.status.${b.status}`)}</Badge>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </>
          );
        }}
      </QueryBoundary>
    </section>
  );
}
