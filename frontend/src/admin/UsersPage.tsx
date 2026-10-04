import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "../api/client";
import { useAdminBusinesses, useAdminUpdateUser, useAdminUsers, useMe } from "../api/hooks";
import { Badge, Card, EmptyState, ErrorText, Input, LinkButton, PageHeader, QueryBoundary } from "../lib/ui";
import { useName } from "../lib/useName";

type User = Schemas["PlatformUserOut"];

/** Every person on the platform, across every business: search, deactivate, grant or remove admin access. */
export function UsersPage() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const users = useAdminUsers(q.trim());
  const businesses = useAdminBusinesses();
  const me = useMe();
  const update = useAdminUpdateUser();

  return (
    <section className="space-y-4">
      <PageHeader title={t("admin.users")} subtitle={t("admin.usersHint")} />
      <Input type="search" placeholder={t("admin.userSearch")} aria-label={t("admin.userSearch")} value={q} onChange={(e) => setQ(e.target.value)} />
      <ErrorText error={update.error} />
      <QueryBoundary query={users}>
        {(rows) => {
          if (rows.length === 0) return <EmptyState>{t("admin.noUsers")}</EmptyState>;
          const team = rows.filter((u) => u.is_platform_admin);
          const owners = rows.filter((u) => u.memberships.some((m) => m.role === "owner"));
          const memberCounts = new Map((businesses.data ?? []).map((b) => [b.id, b.member_count]));
          return (
            <div className="space-y-6">
              <div>
                <h2 className="mb-2 text-lg font-bold">{t("admin.cocreatTeam")}</h2>
                {team.length === 0 ? (
                  <EmptyState>{t("admin.noUsers")}</EmptyState>
                ) : (
                  <ul className="space-y-2">
                    {team.map((u) => (
                      <TeamRow
                        key={u.id}
                        user={u}
                        isSelf={u.id === me.data?.id}
                        onChange={(changes) => update.mutate({ userId: u.id, changes })}
                        pending={update.isPending}
                      />
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h2 className="mb-2 text-lg font-bold">{t("admin.businessOwners")}</h2>
                <p className="mb-2 text-sm text-slate-500">{t("admin.businessOwnersHint")}</p>
                {owners.length === 0 ? (
                  <EmptyState>{t("admin.noUsers")}</EmptyState>
                ) : (
                  <Card className="space-y-0 overflow-x-auto !p-0">
                    <table className="w-full min-w-[640px] text-left text-sm">
                      <thead>
                        <tr className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          <th className="px-4 py-2">{t("admin.colOwner")}</th>
                          <th className="px-4 py-2">{t("admin.businesses")}</th>
                          <th className="px-4 py-2">{t("admin.colWorkspaceUsers")}</th>
                          <th className="px-4 py-2">{t("admin.colStatus")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {owners.map((u) => (
                          <tr key={u.id} className="border-t border-slate-100">
                            <td className="px-4 py-3">
                              <p className={`font-semibold ${u.is_active ? "" : "text-slate-400"}`}>{u.name}</p>
                              <p className="text-sm text-slate-500">{u.phone}</p>
                            </td>
                            <td className="px-4 py-3">
                              <ul className="space-y-0.5">
                                {u.memberships
                                  .filter((m) => m.role === "owner")
                                  .map((m) => (
                                    <li key={m.business_id}>
                                      <Link to={`/admin/businesses/${m.business_id}`} className="text-violet-700">
                                        {m.business_name}
                                      </Link>
                                      {!m.is_active && ` · ${t("common.inactive")}`}
                                    </li>
                                  ))}
                              </ul>
                            </td>
                            <td className="px-4 py-3">
                              {u.memberships
                                .filter((m) => m.role === "owner")
                                .map((m) => memberCounts.get(m.business_id) ?? "—")
                                .join(", ")}
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={u.is_active ? "good" : "bad"}>{u.is_active ? t("common.active") : t("common.inactive")}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Card>
                )}
              </div>
            </div>
          );
        }}
      </QueryBoundary>
    </section>
  );
}

function TeamRow({
  user,
  isSelf,
  onChange,
  pending,
}: {
  user: User;
  isSelf: boolean;
  onChange: (changes: Schemas["PlatformUserUpdate"]) => void;
  pending: boolean;
}) {
  const { t } = useTranslation();
  const name = useName();
  const [roleTitle, setRoleTitle] = useState(user.platform_role_title ?? "");
  const [scopeNote, setScopeNote] = useState(user.platform_scope_note ?? "");

  return (
    <li>
      <Card className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={`truncate text-lg font-semibold ${user.is_active ? "" : "text-slate-400"}`}>{name(user)}</p>
            <p className="text-sm text-slate-500">{user.phone}</p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <Badge tone="brand">{roleTitle || t("admin.platformAdmin")}</Badge>
            {!user.is_active && <Badge tone="bad">{t("common.inactive")}</Badge>}
          </div>
        </div>
        {isSelf ? (
          <p className="text-sm text-slate-400">{t("admin.thisIsYou")}</p>
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                aria-label={t("admin.roleTitle")}
                placeholder={t("admin.roleTitlePlaceholder")}
                value={roleTitle}
                onChange={(e) => setRoleTitle(e.target.value)}
                onBlur={() => onChange({ platform_role_title: roleTitle || null })}
              />
              <Input
                aria-label={t("admin.scopeNote")}
                placeholder={t("admin.scopeNotePlaceholder")}
                value={scopeNote}
                onChange={(e) => setScopeNote(e.target.value)}
                onBlur={() => onChange({ platform_scope_note: scopeNote || null })}
              />
            </div>
            <div className="flex flex-wrap gap-1">
              <LinkButton disabled={pending} onClick={() => onChange({ is_active: !user.is_active })}>
                {user.is_active ? t("common.deactivate") : t("common.activate")}
              </LinkButton>
              <LinkButton disabled={pending} onClick={() => onChange({ is_platform_admin: !user.is_platform_admin })}>
                {user.is_platform_admin ? t("admin.removeAdmin") : t("admin.makeAdmin")}
              </LinkButton>
            </div>
          </>
        )}
      </Card>
    </li>
  );
}
