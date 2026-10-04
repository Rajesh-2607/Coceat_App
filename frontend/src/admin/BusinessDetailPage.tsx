import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import type { Schemas } from "../api/client";
import {
  useAdminAddMember,
  useAdminBusinesses,
  useAdminBusinessLocations,
  useAdminMembers,
  useAdminPlans,
  useAdminSubscription,
  useAdminUpdateBusiness,
  useAdminUpdateMember,
  useAdminUpdateSubscription,
  useAdminVerticals,
} from "../api/hooks";
import { formatDateTime, formatMoney, parseRupees } from "../lib/format";
import { Badge, Button, Card, ErrorText, Field, Input, LinkButton, PageHeader, QueryBoundary, SecondaryButton, Select, Textarea } from "../lib/ui";
import { useName } from "../lib/useName";
import { ModulePicker } from "./ModulePicker";

type Business = Schemas["AdminBusinessOut"];
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
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="space-y-4 lg:col-span-2">
                  <ProfileCard key={`${business.id}:${business.status}:${business.enabled_modules.join()}`} business={business} />
                  <SummaryRow businessId={business.id} />
                  <WorkflowCard verticalKey={business.vertical_key} />
                  <MembersCard businessId={business.id} />
                </div>
                <div className="space-y-4">
                  <StatusSidebar business={business} />
                  <SubscriptionCard businessId={business.id} />
                </div>
              </div>
            </>
          );
        }}
      </QueryBoundary>
    </section>
  );
}

function StatusSidebar({ business }: { business: Business }) {
  const { t, i18n } = useTranslation();
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold">{t("admin.statusCard")}</h2>
      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-slate-500">{t("admin.accountStatus")}</dt>
          <dd>
            <Badge tone={business.status === "active" ? "good" : "bad"}>{t(`admin.status.${business.status}`)}</Badge>
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-slate-500">{t("admin.customerSince")}</dt>
          <dd className="font-medium">{formatDateTime(business.created_at, i18n.language)}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-slate-500">{t("admin.modulesEnabledLabel")}</dt>
          <dd className="font-medium">{business.enabled_modules.length}</dd>
        </div>
      </dl>
      <p className="rounded-xl bg-violet-50 p-3 text-sm text-violet-800">{t("admin.moduleToggleHint")}</p>
    </Card>
  );
}

function SummaryRow({ businessId }: { businessId: string }) {
  const { t } = useTranslation();
  const locations = useAdminBusinessLocations(businessId);
  const members = useAdminMembers(businessId);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card className="space-y-2">
        <h2 className="text-lg font-bold">{t("admin.locationsN", { count: locations.data?.length ?? 0 })}</h2>
        <QueryBoundary query={locations}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="text-sm text-slate-400">{t("admin.noneSet")}</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {rows.map((l) => (
                  <li key={l.id} className="flex justify-between">
                    <span className="font-medium">{l.name}</span>
                    <span className="text-slate-500">{t(`locations.kinds.${l.kind}`)}</span>
                  </li>
                ))}
              </ul>
            )
          }
        </QueryBoundary>
      </Card>
      <Card className="space-y-2">
        <h2 className="text-lg font-bold">{t("admin.usersN", { count: members.data?.length ?? 0 })}</h2>
        <QueryBoundary query={members}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="text-sm text-slate-400">{t("admin.noneSet")}</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {rows
                  .filter((m) => m.is_active)
                  .map((m) => (
                    <li key={m.membership_id} className="flex justify-between">
                      <span className="font-medium">{m.name}</span>
                      <span className="text-slate-500">{t(`roles.${m.role}`)}</span>
                    </li>
                  ))}
              </ul>
            )
          }
        </QueryBoundary>
      </Card>
    </div>
  );
}

function WorkflowCard({ verticalKey }: { verticalKey: string }) {
  const { t } = useTranslation();
  const verticals = useAdminVerticals();
  const vertical = verticals.data?.find((v) => v.key === verticalKey);
  if (!vertical || (vertical.workflow_steps.length === 0 && vertical.workflow_highlights.length === 0)) return null;
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold">{t("admin.workflowTemplate")}</h2>
      {vertical.workflow_steps.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {vertical.workflow_steps.map((s, i) => (
            <div key={s.step} className="flex items-center gap-2">
              <div className="min-w-32 rounded-xl border border-slate-200 px-3 py-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">{t("admin.stepN", { n: s.step })}</p>
                <p className="font-medium">{s.title}</p>
              </div>
              {i < vertical.workflow_steps.length - 1 && <span className="text-slate-400">›</span>}
            </div>
          ))}
        </div>
      )}
      {vertical.workflow_highlights.length > 0 && (
        <div className="grid gap-3 md:grid-cols-3">
          {vertical.workflow_highlights.map((h) => (
            <div key={h.title} className="rounded-xl border border-slate-200 p-3">
              <p className="font-medium text-emerald-700">✓ {h.title}</p>
              <p className="text-sm text-slate-500">{h.description}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
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
      <form onSubmit={submit} className="space-y-5">
        <div>
          <h2 className="text-xl font-bold">{t("admin.profile")}</h2>
          <p className="text-sm text-slate-500">{t("admin.profileHint")}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("admin.name")}>
            <Input required maxLength={120} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
          </Field>
          <Field label={t("admin.nameTa")}>
            <Input maxLength={200} value={nameTa} onChange={(e) => setNameTa(e.target.value)} />
          </Field>
          <Field label={t("admin.gstin")} hint={t("admin.gstinHint")}>
            <Input maxLength={15} value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase())} />
          </Field>
          <Field label={t("admin.phone")}>
            <Input type="tel" maxLength={16} value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <Field label={t("admin.address")} hint={t("admin.addressHint")}>
              <Input maxLength={300} value={address} onChange={(e) => setAddress(e.target.value)} />
            </Field>
          </div>
        </div>
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

/** Which plan the business is on. Informational billing metadata only — no payment gateway is wired up. */
function SubscriptionCard({ businessId }: { businessId: string }) {
  const { t, i18n } = useTranslation();
  const sub = useAdminSubscription(businessId);
  const plans = useAdminPlans(false);
  const update = useAdminUpdateSubscription(businessId);
  const [editing, setEditing] = useState(false);

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-bold">{t("admin.subscription")}</h2>
        {!editing && (
          <SecondaryButton className="!w-auto !min-h-11" onClick={() => setEditing(true)}>
            {t("common.edit")}
          </SecondaryButton>
        )}
      </div>
      <QueryBoundary query={sub}>
        {(s) =>
          editing ? (
            <SubscriptionForm sub={s} plans={plans.data ?? []} update={update} onDone={() => setEditing(false)} />
          ) : (
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={s.status === "active" ? "good" : s.status === "past_due" ? "bad" : s.status === "cancelled" ? "neutral" : "brand"}>
                  {t(`admin.subStatus.${s.status}`)}
                </Badge>
                {s.payment_status === "failed" && <Badge tone="bad">{t("admin.paymentFailed")}</Badge>}
                <span className="font-semibold">{s.plan_key}</span>
              </div>
              <p className="text-slate-600">{s.price_paise != null ? formatMoney(s.price_paise) : t("admin.contactUs")}</p>
              {s.status === "trial" && s.trial_ends_at && (
                <p className="text-sm text-slate-500">{t("admin.trialEnds", { date: formatDateTime(s.trial_ends_at, i18n.language) })}</p>
              )}
              {s.current_period_end && <p className="text-sm text-slate-500">{t("admin.renewsOn", { date: formatDateTime(s.current_period_end, i18n.language) })}</p>}
              {s.cancelled_at && <p className="text-sm text-slate-500">{t("admin.cancelledOn", { date: formatDateTime(s.cancelled_at, i18n.language) })}</p>}
              {s.notes && <p className="text-slate-600">{s.notes}</p>}
            </div>
          )
        }
      </QueryBoundary>
    </Card>
  );
}

function SubscriptionForm({
  sub,
  plans,
  update,
  onDone,
}: {
  sub: Schemas["SubscriptionOut"];
  plans: Schemas["PlanOut"][];
  update: ReturnType<typeof useAdminUpdateSubscription>;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const name = useName();
  const [planKey, setPlanKey] = useState(sub.plan_key);
  const [status, setStatus] = useState(sub.status);
  const [paymentStatus, setPaymentStatus] = useState(sub.payment_status);
  const [price, setPrice] = useState(sub.price_paise != null ? String(sub.price_paise / 100) : "");
  const [renewsOn, setRenewsOn] = useState(sub.current_period_end?.slice(0, 10) ?? "");
  const [notes, setNotes] = useState(sub.notes ?? "");
  const priceValue = price.trim() === "" ? null : parseRupees(price);
  const priceInvalid = price.trim() !== "" && priceValue === null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (priceInvalid) return;
    update.mutate(
      {
        plan_key: planKey,
        status,
        payment_status: paymentStatus,
        price_paise: priceValue,
        current_period_end: renewsOn ? new Date(`${renewsOn}T00:00:00Z`).toISOString() : null,
        notes: notes || null,
      },
      { onSuccess: onDone },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label={t("admin.plan")}>
        <Select value={planKey} onChange={(e) => setPlanKey(e.target.value)}>
          {plans.map((p) => (
            <option key={p.key} value={p.key}>
              {name(p)}
            </option>
          ))}
          {!plans.some((p) => p.key === sub.plan_key) && <option value={sub.plan_key}>{sub.plan_key}</option>}
        </Select>
      </Field>
      <Field label={t("admin.subscriptionStatus")}>
        <Select value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
          <option value="trial">{t("admin.subStatus.trial")}</option>
          <option value="active">{t("admin.subStatus.active")}</option>
          <option value="past_due">{t("admin.subStatus.past_due")}</option>
          <option value="cancelled">{t("admin.subStatus.cancelled")}</option>
        </Select>
      </Field>
      <Field label={t("admin.paymentStatus")} hint={t("admin.paymentStatusHint")}>
        <Select value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value as typeof paymentStatus)}>
          <option value="ok">{t("admin.paymentOk")}</option>
          <option value="failed">{t("admin.paymentFailed")}</option>
        </Select>
      </Field>
      <Field label={`${t("admin.price")} (₹)`} hint={t("admin.subPriceHint")}>
        <Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} aria-invalid={priceInvalid} />
      </Field>
      <Field label={t("admin.renewsOnLabel")}>
        <Input type="date" value={renewsOn} onChange={(e) => setRenewsOn(e.target.value)} />
      </Field>
      <Field label={t("admin.subscriptionNotes")}>
        <Textarea maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <ErrorText error={update.error} />
      <div className="flex gap-2">
        <Button type="submit" className="!w-auto" disabled={update.isPending || priceInvalid}>
          {t("common.save")}
        </Button>
        <SecondaryButton type="button" onClick={onDone}>
          {t("common.cancel")}
        </SecondaryButton>
      </div>
    </form>
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
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("owner");

  function submit(e: FormEvent) {
    e.preventDefault();
    add.mutate(
      { phone, name: nameEn, username, password, role },
      {
        onSuccess: () => {
          setPhone("");
          setNameEn("");
          setUsername("");
          setPassword("");
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
