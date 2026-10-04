import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Schemas } from "../api/client";
import { useProducts, useWastage } from "../api/hooks";
import { formatDateTime, formatQuantity } from "../lib/format";
import { Badge, Button, Card, EmptyState, LinkButton, PageHeader, QueryBoundary } from "../lib/ui";
import { useName, useQuantityLabels } from "../lib/useName";
import { useCurrentLocation } from "./location";
import { ReverseSheet, WastageSheet } from "./stock/StockForms";

export function WastagePage({ context }: { context: Schemas["WorkspaceContextOut"] }) {
  const { t, i18n } = useTranslation();
  const name = useName();
  const labels = useQuantityLabels();
  const { locationId, locations } = useCurrentLocation();
  const wastage = useWastage(locationId);
  const products = useProducts(true);
  const [recording, setRecording] = useState(false);
  const [reversing, setReversing] = useState<string | null>(null);
  const canMove = context.permissions.includes("stock.move");

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.wastage")} />
      {canMove && <Button onClick={() => setRecording(true)}>🗑️ {t("wastage.record")}</Button>}
      <QueryBoundary query={wastage}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{t("wastage.empty")}</EmptyState>
          ) : (
            <ul className="space-y-2">
              {rows.map((w) => {
                const p = products.data?.find((x) => x.id === w.product_id);
                const location = locations.find((l) => l.id === w.location_id);
                return (
                  <li key={w.id}>
                    <Card className="space-y-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className={`truncate text-lg font-semibold ${w.reversed ? "text-slate-400 line-through" : ""}`}>
                          {p ? name(p) : "…"}
                        </p>
                        <p className={`shrink-0 text-lg font-bold ${w.reversed ? "text-slate-400 line-through" : "text-rose-600"}`}>
                          {formatQuantity(w.quantity, p?.kind ?? "count", labels)}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
                        <Badge tone="warn">{t(`wastage.reasons.${w.reason_code}`)}</Badge>
                        {location && <span>{name(location)}</span>}
                        <span>{formatDateTime(w.created_at, i18n.language)}</span>
                        {w.reversed && <Badge>{t("stock.reversed")}</Badge>}
                      </div>
                      {w.note && <p className="text-slate-600">{w.note}</p>}
                      {canMove && !w.reversed && <LinkButton onClick={() => setReversing(w.movement_id)}>{t("stock.reverse")}</LinkButton>}
                    </Card>
                  </li>
                );
              })}
            </ul>
          )
        }
      </QueryBoundary>
      {recording && <WastageSheet onClose={() => setRecording(false)} />}
      {reversing && <ReverseSheet movementId={reversing} onClose={() => setReversing(null)} />}
    </section>
  );
}
