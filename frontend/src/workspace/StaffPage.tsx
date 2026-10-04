import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useAddStaff, useLocations, useStaff, useUpdateStaff } from "../api/hooks";
import { Badge, Button, Card, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, Select, Sheet } from "../lib/ui";
import { useName } from "../lib/useName";

type Staff = Schemas["StaffOut"];
type Role = Schemas["StaffOut"]["role"];
const ROLES: Role[] = ["owner", "manager", "billing", "stock", "viewer"];

export function StaffPage({ context, meId }: { context: Schemas["WorkspaceContextOut"]; meId: string }) {
  const { t } = useTranslation();
  const name = useName();
  const staff = useStaff();
  const locations = useLocations();
  const update = useUpdateStaff();
  const [editing, setEditing] = useState<Staff | "new" | null>(null);
  const canManage = context.permissions.includes("staff.manage");

  const locationNames = (ids: string[] | null) =>
    ids === null ? t("staff.allLocations") : ids.map((id) => locations.data?.find((l) => l.id === id)).map((l) => (l ? name(l) : "…")).join(", ");

  return (
    <section className="space-y-4">
      <PageHeader
        title={t("nav.staff")}
        actions={canManage ? <Button className="!w-auto" onClick={() => setEditing("new")}>+ {t("staff.add")}</Button> : undefined}
      />
      <ErrorText error={update.error} />
      <QueryBoundary query={staff}>
        {(rows) => (
          <ul className="space-y-2">
            {rows.map((s) => (
              <li key={s.membership_id}>
                <Card className="space-y-1">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className={`truncate text-lg font-semibold ${s.is_active ? "" : "text-slate-400"}`}>{name(s)}</p>
                      <p className="text-sm text-slate-500">{s.phone}</p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge tone="brand">{t(`roles.${s.role}`)}</Badge>
                      {!s.is_active && <Badge tone="warn">{t("common.inactive")}</Badge>}
                    </div>
                  </div>
                  <p className="text-sm text-slate-500">{locationNames(s.location_ids)}</p>
                  {canManage && s.user_id !== meId && (
                    <div className="flex gap-1">
                      <LinkButton onClick={() => setEditing(s)}>{t("common.edit")}</LinkButton>
                      <LinkButton
                        disabled={update.isPending}
                        onClick={() => update.mutate({ membershipId: s.membership_id, changes: { is_active: !s.is_active } })}
                      >
                        {s.is_active ? t("common.deactivate") : t("common.activate")}
                      </LinkButton>
                    </div>
                  )}
                </Card>
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
      {editing && <StaffSheet staff={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function StaffSheet({ staff, onClose }: { staff: Staff | null; onClose: () => void }) {
  const { t } = useTranslation();
  const name = useName();
  const locations = useLocations();
  const add = useAddStaff();
  const update = useUpdateStaff();
  const [nameEn, setNameEn] = useState(staff?.name ?? "");
  const [phone, setPhone] = useState(staff?.phone ?? "");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(staff?.role ?? "billing");
  const [restricted, setRestricted] = useState(staff?.location_ids != null);
  const [chosen, setChosen] = useState<string[]>(staff?.location_ids ?? []);
  const write = staff ? update : add;
  const locationIds = restricted ? chosen : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (staff) {
      update.mutate({ membershipId: staff.membership_id, changes: { role, location_ids: locationIds } }, { onSuccess: onClose });
    } else {
      add.mutate(
        { name: nameEn, phone, username, password, role, location_ids: locationIds },
        { onSuccess: onClose },
      );
    }
  }

  return (
    <Sheet title={staff ? t("staff.edit") : t("staff.add")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {!staff && (
          <>
            <Field label={t("staff.name")}>
              <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
            </Field>
            <Field label={t("staff.phone")}>
              <Input required type="tel" inputMode="numeric" maxLength={14} value={phone} onChange={(e) => setPhone(e.target.value)} />
            </Field>
            <Field label={t("login.username")} hint={t("login.usernameHint")}>
              <Input
                required
                autoCapitalize="none"
                autoComplete="off"
                pattern="[a-z0-9._\-]{3,40}"
                maxLength={40}
                value={username}
                onChange={(e) => setUsername(e.target.value.toLowerCase())}
              />
            </Field>
            <Field label={t("login.password")} hint={t("login.passwordHint")}>
              <Input
                required
                type="password"
                minLength={10}
                maxLength={200}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </>
        )}
        <Field label={t("staff.role")} hint={t(`staff.roleHint.${role}`)}>
          <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`roles.${r}`)}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex min-h-11 items-center gap-2 text-lg">
          <input type="checkbox" className="size-5" checked={restricted} onChange={(e) => setRestricted(e.target.checked)} />
          {t("staff.restrictLocations")}
        </label>
        {restricted && (
          <div className="space-y-1 rounded-2xl bg-slate-50 p-3">
            {(locations.data ?? []).map((l) => (
              <label key={l.id} className="flex min-h-11 items-center gap-2 text-lg">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={chosen.includes(l.id)}
                  onChange={(e) => setChosen((prev) => (e.target.checked ? [...prev, l.id] : prev.filter((x) => x !== l.id)))}
                />
                {name(l)}
              </label>
            ))}
          </div>
        )}
        <ErrorText error={write.error} />
        <Button type="submit" disabled={write.isPending || (restricted && chosen.length === 0)}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
