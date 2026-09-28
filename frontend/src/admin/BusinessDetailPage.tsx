import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../api/client";
import {
  useAdminAddMember,
  useAdminBusinesses,
  useAdminMembers,
  useAdminUpdateBusiness,
  useAdminUpdateMember,
} from "../api/hooks";
import { Badge, Button, Card, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, SecondaryButton, Select } from "../lib/ui";
import { useName } from "../lib/useName";
import { ModulePicker } from "./ModulePicker";

type Business = Schemas["BusinessOut"];
type Role = Schemas["MemberIn"]["role"];
type ModuleList = NonNullable<Schemas["BusinessUpdate"]["enabled_modules"]>;
const ROLES: Role[] = ["owner", "manager", "billing", "stock", "viewer"];

export function BusinessDetailPage() {
  const { t } = useTranslation();
  const name = useName();
  const { id = "" } = useParams();
  const businesses = useAdminBusinesses();
  return (
    <section className="space-y-5">
      <Link to="/admin/businesses" className="inline-flex min-h-11 items-center font-medium text-violet-700">
        ← {t("admin.businesses")}
      </Link>
      <QueryBoundary query={businesses}>
        {(rows) => {
          const business = rows.find((b) => b.id === id);
          if (!business) return <ErrorText error={{ code: "not_found" }} />;
          return (
            <>
              <PageHeader
                title={name(business)}
                subtitle={business.vertical_key}
                actions={<Badge tone={business.status === "active" ? "good" : "bad"}>{t(`admin.status.${business.status}`)}</Badge>}
              />
              <ProfileCard key={`${business.id}:${business.status}:${business.enabled_modules.join()}`} business={business} />
              <MembersCard businessId={business.id} />
            </>
          );
        }}
      </QueryBoundary>
    </section>
  );
}

function ProfileCard({ business }: { business: Business }) {
  const { t } = useTranslation();
  const update = useAdminUpdateBusiness(business.id);
  const [nameEn, setNameEn] = useState(business.name);
  const [nameTa, setNameTa] = useState(business.name_ta ?? "");
  const [gstin, setGstin] = useState(business.gstin ?? "");
  const [address, setAddress] = useState(business.address ?? "");
  const [phone, setPhone] = useState(business.phone ?? "");
  const [modules, setModules] = useState(business.enabled_modules);
  const [saved, setSaved] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(false);
    update.mutate(
      {
        name: nameEn,
        name_ta: nameTa || null,
        gstin: gstin || null,
        address: address || null,
        phone: phone || null,
        enabled_modules: modules as ModuleList,
      },
      { onSuccess: () => setSaved(true) },
    );
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4">
        <h2 className="text-xl font-bold">{t("admin.profile")}</h2>
        <Field label={t("admin.name")}>
          <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("admin.nameTa")}>
          <Input maxLength={200} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
        </Field>
        <Field label={t("admin.gstin")} hint={t("admin.gstinHint")}>
          <Input maxLength={15} value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase())} />
        </Field>
        <Field label={t("admin.address")} hint={t("admin.addressHint")}>
          <Input maxLength={300} value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Field label={t("admin.phone")}>
          <Input type="tel" maxLength={16} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </Field>
        <ModulePicker value={modules} onChange={setModules} />
        <ErrorText error={update.error} />
        {saved && <p className="text-emerald-700">✓ {t("common.saved")}</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" className="!w-auto" disabled={update.isPending}>
            {t("common.save")}
          </Button>
          <SecondaryButton
            type="button"
            disabled={update.isPending}
            onClick={() => update.mutate({ status: business.status === "active" ? "suspended" : "active" })}
          >
            {business.status === "active" ? t("admin.suspend") : t("admin.activate")}
          </SecondaryButton>
        </div>
      </form>
    </Card>
  );
}

function MembersCard({ businessId }: { businessId: string }) {
  const { t } = useTranslation();
  const name = useName();
  const members = useAdminMembers(businessId);
  const add = useAdminAddMember(businessId);
  const update = useAdminUpdateMember(businessId);
  const [phone, setPhone] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [role, setRole] = useState<Role>("owner");

  function submit(e: FormEvent) {
    e.preventDefault();
    add.mutate(
      { phone, name: nameEn, role },
      {
        onSuccess: () => {
          setPhone("");
          setNameEn("");
        },
      },
    );
  }

  return (
    <Card className="space-y-4">
      <h2 className="text-xl font-bold">{t("admin.members")}</h2>
      <ErrorText error={update.error} />
      <QueryBoundary query={members}>
        {(rows) => (
          <ul className="divide-y">
            {rows.map((m) => (
              <li key={m.membership_id} className="flex min-h-14 items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className={`truncate text-lg font-semibold ${m.is_active ? "" : "text-slate-400"}`}>{name(m)}</p>
                  <p className="text-sm text-slate-500">{m.phone}</p>
                </div>
                <div className="flex items-center gap-1">
                  <Badge tone="brand">{t(`roles.${m.role}`)}</Badge>
                  <LinkButton
                    disabled={update.isPending}
                    onClick={() => update.mutate({ membershipId: m.membership_id, changes: { is_active: !m.is_active } })}
                  >
                    {m.is_active ? t("common.deactivate") : t("common.activate")}
                  </LinkButton>
                </div>
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
      <form onSubmit={submit} className="space-y-3 rounded-2xl bg-slate-50 p-3">
        <h3 className="font-semibold">{t("admin.addMember")}</h3>
        <Field label={t("staff.name")}>
          <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </Field>
        <Field label={t("staff.phone")}>
          <Input required type="tel" inputMode="numeric" maxLength={14} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </Field>
        <Field label={t("staff.role")}>
          <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`roles.${r}`)}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorText error={add.error} />
        <Button type="submit" disabled={add.isPending}>
          {t("common.save")}
        </Button>
      </form>
    </Card>
  );
}
