import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Schemas } from "../../api/client";
import { useCrateBalances, useParties, useRecordCrates } from "../../api/hooks";
import { Button, Card, EmptyState, ErrorText, Field, Input, QueryBoundary, Select, Sheet } from "../../lib/ui";
import { useName } from "../../lib/useName";
import { useCurrentLocation } from "../location";

/** Which parties are holding our crates. Customers and suppliers both can. */
export function CratesTab({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const name = useName();
  const balances = useCrateBalances();
  const customers = useParties("customers", "", true);
  const suppliers = useParties("suppliers", "", true);
  const [recording, setRecording] = useState(false);

  const find = (id: string) => {
    const c = customers.data?.find((p) => p.id === id);
    if (c) return { party: c, to: `/w/customers/${id}` };
    const s = suppliers.data?.find((p) => p.id === id);
    return s ? { party: s, to: `/w/suppliers/${id}` } : null;
  };

  return (
    <div className="space-y-3">
      {canManage && <Button onClick={() => setRecording(true)}>📦 {t("crates.record")}</Button>}
      <QueryBoundary query={balances}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("crates.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((b) => {
                const found = find(b.party_id);
                return (
                  <li key={b.party_id}>
                    <Card className="flex items-center justify-between gap-3">
                      {found ? (
                        <Link to={found.to} className="min-w-0 truncate text-lg font-semibold text-violet-700">
                          {name(found.party)}
                        </Link>
                      ) : (
                        <span className="text-lg">…</span>
                      )}
                      <p className={`shrink-0 text-xl font-bold ${b.crates_held < 0 ? "text-rose-600" : ""}`}>
                        {b.crates_held} <span className="text-sm font-normal text-slate-500">{t("crates.crates")}</span>
                      </p>
                    </Card>
                  </li>
                );
              })}
            </ul>
          )
        }
      </QueryBoundary>
      {recording && (
        <RecordSheet
          customers={customers.data ?? []}
          suppliers={suppliers.data ?? []}
          onClose={() => setRecording(false)}
        />
      )}
    </div>
  );
}

function RecordSheet({
  customers,
  suppliers,
  onClose,
}: {
  customers: Schemas["PartyOut"][];
  suppliers: Schemas["PartyOut"][];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const name = useName();
  const { locationId, locations } = useCurrentLocation();
  const record = useRecordCrates();
  const [party, setParty] = useState("");
  const [direction, setDirection] = useState<Schemas["CrateEntryIn"]["direction"]>("issued");
  const [qty, setQty] = useState("");
  const [location, setLocation] = useState(locationId ?? "");
  const quantity = /^\d+$/.test(qty) && Number(qty) > 0 ? Number(qty) : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!quantity) return;
    record.mutate({ party_id: party, direction, quantity, location_id: location || null }, { onSuccess: onClose });
  }

  return (
    <Sheet title={t("crates.record")} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label={t("crates.party")}>
          <Select required value={party} onChange={(e) => setParty(e.target.value)}>
            <option value="">{t("common.choose")}</option>
            <optgroup label={t("nav.customers")}>
              {customers.map((p) => (
                <option key={p.id} value={p.id}>
                  {name(p)}
                </option>
              ))}
            </optgroup>
            <optgroup label={t("nav.suppliers")}>
              {suppliers.map((p) => (
                <option key={p.id} value={p.id}>
                  {name(p)}
                </option>
              ))}
            </optgroup>
          </Select>
        </Field>
        <div className="flex gap-2" role="radiogroup" aria-label={t("crates.direction")}>
          {(["issued", "returned"] as const).map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={direction === d}
              onClick={() => setDirection(d)}
              className={`min-h-12 flex-1 rounded-xl border text-lg font-medium ${direction === d ? "border-violet-700 bg-violet-50 text-violet-700" : "border-slate-300"}`}
            >
              {t(`crates.${d}`)}
            </button>
          ))}
        </div>
        <Field label={t("crates.count")}>
          <Input required inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))} />
        </Field>
        {locations.length > 0 && (
          <Field label={t("stock.location")}>
            <Select value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">{t("common.none")}</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {name(l)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <ErrorText error={record.error} />
        <Button type="submit" disabled={record.isPending || !party || !quantity}>
          {t("common.save")}
        </Button>
      </form>
    </Sheet>
  );
}
