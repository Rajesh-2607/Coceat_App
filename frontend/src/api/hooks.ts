import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api, ApiError, newIdempotencyKey, unwrap, type Schemas } from "./client";

/** Retry only network failures and 5xx; a 4xx (validation, conflict, permission) will not change on retry. */
function retryTransient(failureCount: number, error: unknown): boolean {
  return failureCount < 3 && !(error instanceof ApiError && error.status < 500);
}

export type PartyKind = "customers" | "suppliers";

export const queryKeys = {
  me: ["me"] as const,
  context: ["w", "context"] as const,
  home: ["w", "home"] as const,
  locations: ["w", "locations"] as const,
  units: ["w", "units"] as const,
  grades: ["w", "grades"] as const,
  products: ["w", "products"] as const,
  parties: (kind: PartyKind) => ["w", kind] as const,
  party: (kind: PartyKind, id: string) => ["w", kind, id] as const,
  balances: ["w", "stock", "balances"] as const,
  movements: ["w", "stock", "movements"] as const,
  transfers: ["w", "stock", "transfers"] as const,
  wastage: ["w", "stock", "wastage"] as const,
  crates: ["w", "crates"] as const,
  bills: ["w", "bills"] as const,
  purchases: ["w", "purchases"] as const,
  payments: ["w", "money", "payments"] as const,
  reports: ["w", "reports"] as const,
  staff: ["w", "staff"] as const,
  audit: ["w", "audit"] as const,
  adminBusinesses: ["admin", "businesses"] as const,
  adminVerticals: ["admin", "verticals"] as const,
  adminUsers: ["admin", "users"] as const,
  adminPlans: ["admin", "plans"] as const,
  adminSubscriptions: ["admin", "subscriptions"] as const,
  adminSettings: ["admin", "settings"] as const,
};

/**
 * A write with an idempotency key. The key is created once per user action (when `mutate` is called),
 * travels in the variables, and so is reused by TanStack's automatic retries of that same action.
 */
function useWrite<B, R>(send: (body: B, key: string) => Promise<R>, invalidate: QueryKey[]) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: ({ body, key }: { body: B; key: string }) => send(body, key),
    retry: retryTransient,
    onSuccess: () => Promise.all(invalidate.map((queryKey) => qc.invalidateQueries({ queryKey }))),
  });
  return {
    /** Pass `key` to keep one key for one user action across re-taps (a sale bill). Default: a fresh key per call. */
    mutate: (body: B, options?: Parameters<typeof m.mutate>[1], key?: string) =>
      m.mutate({ body, key: key ?? newIdempotencyKey() }, options),
    mutateAsync: (body: B) => m.mutateAsync({ body, key: newIdempotencyKey() }),
    isPending: m.isPending,
    error: m.error,
    reset: m.reset,
  };
}

const idemHeader = (key: string) => ({ header: { "Idempotency-Key": key } });

/* ---- session ---------------------------------------------------------------------------------------- */

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: async () => unwrap(await api.GET("/api/me")),
    retry: false,
  });
}

export function useWorkspaceContext(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.context,
    queryFn: async () => unwrap(await api.GET("/api/w/context")),
    enabled,
    retry: false,
  });
}

export function useRequestOtp() {
  return useMutation({
    mutationFn: async (phone: string) => unwrap(await api.POST("/api/auth/otp/request", { body: { phone } })),
  });
}

export function useVerifyOtp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["OtpVerifyIn"]) => unwrap(await api.POST("/api/auth/otp/verify", { body })),
    onSuccess: (me) => {
      qc.setQueryData(queryKeys.me, me);
    },
  });
}

export function useSelectBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (business_id: string) =>
      unwrap(await api.PUT("/api/me/business", { body: { business_id } })),
    onSuccess: (me) => {
      qc.setQueryData(queryKeys.me, me);
      void qc.invalidateQueries({ queryKey: ["w"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout");
    },
    onSettled: () => qc.clear(),
  });
}

/* ---- home ------------------------------------------------------------------------------------------- */

export function useHome() {
  return useQuery({ queryKey: queryKeys.home, queryFn: async () => unwrap(await api.GET("/api/w/home")) });
}

/* ---- locations -------------------------------------------------------------------------------------- */

export function useLocations() {
  return useQuery({
    queryKey: queryKeys.locations,
    queryFn: async () => unwrap(await api.GET("/api/w/locations")),
  });
}

export function useCreateLocation() {
  return useWrite(
    async (body: Schemas["LocationCreate"], key) =>
      unwrap(await api.POST("/api/w/locations", { body, params: idemHeader(key) })),
    [queryKeys.locations],
  );
}

export function useUpdateLocation(id: string) {
  return useWrite(
    async (body: Schemas["LocationUpdate"], key) =>
      unwrap(
        await api.PATCH("/api/w/locations/{location_id}", {
          body,
          params: { ...idemHeader(key), path: { location_id: id } },
        }),
      ),
    [queryKeys.locations],
  );
}

/* ---- catalog ---------------------------------------------------------------------------------------- */

export function useUnits() {
  return useQuery({ queryKey: queryKeys.units, queryFn: async () => unwrap(await api.GET("/api/w/units")) });
}

export function useCreateUnit() {
  return useWrite(
    async (body: Schemas["UnitCreate"], key) => unwrap(await api.POST("/api/w/units", { body, params: idemHeader(key) })),
    [queryKeys.units],
  );
}

export function useGrades() {
  return useQuery({ queryKey: queryKeys.grades, queryFn: async () => unwrap(await api.GET("/api/w/grades")) });
}

export function useCreateGrade() {
  return useWrite(
    async (body: Schemas["GradeCreate"], key) => unwrap(await api.POST("/api/w/grades", { body, params: idemHeader(key) })),
    [queryKeys.grades],
  );
}

export function useUpdateGrade(id: string) {
  return useWrite(
    async (body: Schemas["GradeUpdate"], key) =>
      unwrap(
        await api.PATCH("/api/w/grades/{grade_id}", { body, params: { ...idemHeader(key), path: { grade_id: id } } }),
      ),
    [queryKeys.grades],
  );
}

export function useProducts(includeInactive = false) {
  return useQuery({
    queryKey: [...queryKeys.products, includeInactive],
    queryFn: async () =>
      unwrap(await api.GET("/api/w/products", { params: { query: { include_inactive: includeInactive } } })),
  });
}

export function useCreateProduct() {
  return useWrite(
    async (body: Schemas["ProductCreate"], key) =>
      unwrap(await api.POST("/api/w/products", { body, params: idemHeader(key) })),
    [queryKeys.products],
  );
}

export function useUpdateProduct(id: string) {
  return useWrite(
    async (body: Schemas["ProductUpdate"], key) =>
      unwrap(
        await api.PATCH("/api/w/products/{product_id}", {
          body,
          params: { ...idemHeader(key), path: { product_id: id } },
        }),
      ),
    [queryKeys.products],
  );
}

export function useAddVariety(productId: string) {
  return useWrite(
    async (body: Schemas["VarietyCreate"], key) =>
      unwrap(
        await api.POST("/api/w/products/{product_id}/varieties", {
          body,
          params: { ...idemHeader(key), path: { product_id: productId } },
        }),
      ),
    [queryKeys.products],
  );
}

/* ---- parties (customers / suppliers) ---------------------------------------------------------------- */

export function useParties(kind: PartyKind, q: string, includeInactive = false) {
  const query = { q: q || undefined, include_inactive: includeInactive };
  return useQuery({
    queryKey: [...queryKeys.parties(kind), "list", q, includeInactive],
    queryFn: async () =>
      unwrap(
        kind === "customers"
          ? await api.GET("/api/w/customers", { params: { query } })
          : await api.GET("/api/w/suppliers", { params: { query } }),
      ),
  });
}

export function useParty(kind: PartyKind, id: string) {
  return useQuery({
    queryKey: [...queryKeys.party(kind, id), "detail"],
    queryFn: async () =>
      unwrap(
        kind === "customers"
          ? await api.GET("/api/w/customers/{party_id}", { params: { path: { party_id: id } } })
          : await api.GET("/api/w/suppliers/{party_id}", { params: { path: { party_id: id } } }),
      ),
  });
}

export function useCreateParty(kind: PartyKind) {
  return useWrite(
    async (body: Schemas["PartyCreate"], key) =>
      unwrap(
        kind === "customers"
          ? await api.POST("/api/w/customers", { body, params: idemHeader(key) })
          : await api.POST("/api/w/suppliers", { body, params: idemHeader(key) }),
      ),
    [queryKeys.parties(kind), queryKeys.home],
  );
}

export function useUpdateParty(kind: PartyKind, id: string) {
  return useWrite(
    async (body: Schemas["PartyUpdate"], key) => {
      const params = { ...idemHeader(key), path: { party_id: id } };
      return unwrap(
        kind === "customers"
          ? await api.PATCH("/api/w/customers/{party_id}", { body, params })
          : await api.PATCH("/api/w/suppliers/{party_id}", { body, params }),
      );
    },
    [queryKeys.parties(kind), queryKeys.home],
  );
}

export function usePartyLedger(kind: PartyKind, id: string) {
  return useQuery({
    queryKey: [...queryKeys.party(kind, id), "ledger"],
    queryFn: async () =>
      unwrap(
        kind === "customers"
          ? await api.GET("/api/w/customers/{party_id}/ledger", { params: { path: { party_id: id } } })
          : await api.GET("/api/w/suppliers/{party_id}/ledger", { params: { path: { party_id: id } } }),
      ),
  });
}

export function useAdjustParty(kind: PartyKind, id: string) {
  return useWrite(
    async (body: Schemas["PartyAdjustmentIn"], key) => {
      const params = { ...idemHeader(key), path: { party_id: id } };
      return unwrap(
        kind === "customers"
          ? await api.POST("/api/w/customers/{party_id}/adjustments", { body, params })
          : await api.POST("/api/w/suppliers/{party_id}/adjustments", { body, params }),
      );
    },
    [queryKeys.party(kind, id), queryKeys.parties(kind), queryKeys.home],
  );
}

export function usePartyCrates(kind: PartyKind, id: string) {
  return useQuery({
    queryKey: [...queryKeys.party(kind, id), "crates"],
    queryFn: async () =>
      unwrap(
        kind === "customers"
          ? await api.GET("/api/w/customers/{party_id}/crates", { params: { path: { party_id: id } } })
          : await api.GET("/api/w/suppliers/{party_id}/crates", { params: { path: { party_id: id } } }),
      ),
  });
}

export function useAdjustPartyCrates(kind: PartyKind, id: string) {
  return useWrite(
    async (body: Schemas["CrateAdjustmentIn"], key) => {
      const params = { ...idemHeader(key), path: { party_id: id } };
      return unwrap(
        kind === "customers"
          ? await api.POST("/api/w/customers/{party_id}/crate-adjustments", { body, params })
          : await api.POST("/api/w/suppliers/{party_id}/crate-adjustments", { body, params }),
      );
    },
    [queryKeys.party(kind, id), queryKeys.parties(kind), queryKeys.crates, queryKeys.home],
  );
}

/* ---- crates ----------------------------------------------------------------------------------------- */

export function useCrateBalances() {
  return useQuery({
    queryKey: [...queryKeys.crates, "balances"],
    queryFn: async () => unwrap(await api.GET("/api/w/crates/balances", { params: { query: {} } })),
  });
}

export function useRecordCrates() {
  return useWrite(
    async (body: Schemas["CrateEntryIn"], key) =>
      unwrap(await api.POST("/api/w/crates/entries", { body, params: idemHeader(key) })),
    [queryKeys.crates, ["w", "customers"], ["w", "suppliers"], queryKeys.home],
  );
}

/* ---- stock ------------------------------------------------------------------------------------------ */

const stockChanged = [queryKeys.balances, queryKeys.movements, queryKeys.transfers, queryKeys.wastage, queryKeys.home];

export function useStockBalances(locationId: string | null) {
  return useQuery({
    queryKey: [...queryKeys.balances, locationId],
    queryFn: async () =>
      unwrap(await api.GET("/api/w/stock/balances", { params: { query: { location_id: locationId ?? undefined } } })),
  });
}

export function useMovements(locationId: string | null) {
  return useQuery({
    queryKey: [...queryKeys.movements, locationId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/w/stock/movements", { params: { query: { location_id: locationId ?? undefined, limit: 100 } } }),
      ),
  });
}

export function useTransfers() {
  return useQuery({
    queryKey: queryKeys.transfers,
    queryFn: async () => unwrap(await api.GET("/api/w/stock/transfers", { params: { query: { limit: 50 } } })),
  });
}

export function useWastage(locationId: string | null) {
  return useQuery({
    queryKey: [...queryKeys.wastage, locationId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/w/stock/wastage", { params: { query: { location_id: locationId ?? undefined, limit: 100 } } }),
      ),
  });
}

export function useRecordOpening() {
  return useWrite(
    async (body: Schemas["OpeningStockIn"], key) =>
      unwrap(await api.POST("/api/w/stock/opening", { body, params: idemHeader(key) })),
    stockChanged,
  );
}

export function useAdjustStock() {
  return useWrite(
    async (body: Schemas["StockAdjustmentIn"], key) =>
      unwrap(await api.POST("/api/w/stock/adjustments", { body, params: idemHeader(key) })),
    stockChanged,
  );
}

export function useTransferStock() {
  return useWrite(
    async (body: Schemas["TransferIn"], key) =>
      unwrap(await api.POST("/api/w/stock/transfers", { body, params: idemHeader(key) })),
    stockChanged,
  );
}

export function useRecordWastage() {
  return useWrite(
    async (body: Schemas["WastageIn"], key) =>
      unwrap(await api.POST("/api/w/stock/wastage", { body, params: idemHeader(key) })),
    stockChanged,
  );
}

export function useReverseMovement() {
  return useWrite(
    async ({ movementId, reason }: { movementId: string; reason: string }, key) =>
      unwrap(
        await api.POST("/api/w/stock/movements/{movement_id}/reverse", {
          body: { reason },
          params: { ...idemHeader(key), path: { movement_id: movementId } },
        }),
      ),
    stockChanged,
  );
}

/* ---- staff and audit -------------------------------------------------------------------------------- */

export function useStaff() {
  return useQuery({ queryKey: queryKeys.staff, queryFn: async () => unwrap(await api.GET("/api/w/staff")) });
}

export function useAddStaff() {
  return useWrite(
    async (body: Schemas["MemberIn"], key) => unwrap(await api.POST("/api/w/staff", { body, params: idemHeader(key) })),
    [queryKeys.staff],
  );
}

export function useUpdateStaff() {
  return useWrite(
    async ({ membershipId, changes }: { membershipId: string; changes: Schemas["StaffUpdate"] }, key) =>
      unwrap(
        await api.PATCH("/api/w/staff/{membership_id}", {
          body: changes,
          params: { ...idemHeader(key), path: { membership_id: membershipId } },
        }),
      ),
    [queryKeys.staff],
  );
}

export type AuditFilters = { action?: string; entity_type?: string; actor_user_id?: string; date_from?: string; date_to?: string };

export function useAuditEvents(filters: AuditFilters) {
  return useQuery({
    queryKey: [...queryKeys.audit, filters],
    queryFn: async () =>
      unwrap(await api.GET("/api/w/audit-events", { params: { query: { ...filters, limit: 100 } } })),
  });
}

/* ---- platform admin --------------------------------------------------------------------------------- */

export function useAdminBusinesses() {
  return useQuery({
    queryKey: queryKeys.adminBusinesses,
    queryFn: async () => unwrap(await api.GET("/api/admin/businesses")),
  });
}

export function useAdminVerticals() {
  return useQuery({
    queryKey: queryKeys.adminVerticals,
    queryFn: async () => unwrap(await api.GET("/api/admin/verticals")),
  });
}

export function useAdminBusinessLocations(businessId: string) {
  return useQuery({
    queryKey: ["admin", "locations", businessId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/admin/businesses/{business_id}/locations", { params: { path: { business_id: businessId } } }),
      ),
  });
}

export function useAdminMembers(businessId: string) {
  return useQuery({
    queryKey: ["admin", "members", businessId],
    queryFn: async () =>
      unwrap(await api.GET("/api/admin/businesses/{business_id}/members", { params: { path: { business_id: businessId } } })),
  });
}

/** Admin writes are not PWA writes (no idempotency key), so these are plain mutations. */
export function useAdminCreateBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["BusinessCreate"]) => unwrap(await api.POST("/api/admin/businesses", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminBusinesses }),
  });
}

export function useAdminUpdateBusiness(businessId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["BusinessUpdate"]) =>
      unwrap(await api.PATCH("/api/admin/businesses/{business_id}", { body, params: { path: { business_id: businessId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminBusinesses }),
  });
}

export function useAdminAddMember(businessId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["MemberIn"]) =>
      unwrap(await api.PUT("/api/admin/businesses/{business_id}/members", { body, params: { path: { business_id: businessId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "members", businessId] }),
  });
}

export function useAdminUpdateMember(businessId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ membershipId, changes }: { membershipId: string; changes: Schemas["StaffUpdate"] }) =>
      unwrap(
        await api.PATCH("/api/admin/businesses/{business_id}/members/{membership_id}", {
          body: changes,
          params: { path: { business_id: businessId, membership_id: membershipId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "members", businessId] }),
  });
}

export function useAdminCreateVertical() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["VerticalCreate"]) => unwrap(await api.POST("/api/admin/verticals", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminVerticals }),
  });
}

export function useAdminUpdateVertical(key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["VerticalUpdate"]) =>
      unwrap(await api.PATCH("/api/admin/verticals/{key}", { body, params: { path: { key } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminVerticals }),
  });
}

export function useAdminCompleteSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (businessId: string) =>
      unwrap(
        await api.POST("/api/admin/businesses/{business_id}/complete-setup", {
          params: { path: { business_id: businessId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminBusinesses }),
  });
}

export function useAdminUsers(q: string) {
  return useQuery({
    queryKey: [...queryKeys.adminUsers, q],
    queryFn: async () => unwrap(await api.GET("/api/admin/users", { params: { query: { q: q || undefined } } })),
  });
}

export function useAdminUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, changes }: { userId: string; changes: Schemas["PlatformUserUpdate"] }) =>
      unwrap(await api.PATCH("/api/admin/users/{user_id}", { body: changes, params: { path: { user_id: userId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminUsers }),
  });
}

export { newIdempotencyKey };


/* ---- billing ---------------------------------------------------------------------------------------- */

const moneyMoved = [queryKeys.bills, queryKeys.balances, queryKeys.movements, ["w", "customers"], ["w", "suppliers"], queryKeys.payments, queryKeys.reports, queryKeys.home];

export type BillFilters = { q?: string; date_from?: string; date_to?: string; party_id?: string; status?: "active" | "void" };

export function useBills(filters: BillFilters) {
  return useQuery({
    queryKey: [...queryKeys.bills, "list", filters],
    queryFn: async () => unwrap(await api.GET("/api/w/bills", { params: { query: { ...filters, limit: 100 } } })),
  });
}

export function useBill(id: string) {
  return useQuery({
    queryKey: [...queryKeys.bills, "detail", id],
    queryFn: async () => unwrap(await api.GET("/api/w/bills/{bill_id}", { params: { path: { bill_id: id } } })),
  });
}

export function useCreateBill() {
  return useWrite(
    async (body: Schemas["SaleIn"], key) => unwrap(await api.POST("/api/w/bills", { body, params: idemHeader(key) })),
    moneyMoved,
  );
}

export function useVoidBill(id: string) {
  return useWrite(
    async (reason: string, key) =>
      unwrap(
        await api.POST("/api/w/bills/{bill_id}/void", {
          body: { reason },
          params: { ...idemHeader(key), path: { bill_id: id } },
        }),
      ),
    moneyMoved,
  );
}

export function useBillReturns(id: string) {
  return useQuery({
    queryKey: [...queryKeys.bills, "returns", id],
    queryFn: async () => unwrap(await api.GET("/api/w/bills/{bill_id}/returns", { params: { path: { bill_id: id } } })),
  });
}

export function useReturnGoods(id: string) {
  return useWrite(
    async (body: Schemas["ReturnIn"], key) =>
      unwrap(
        await api.POST("/api/w/bills/{bill_id}/returns", { body, params: { ...idemHeader(key), path: { bill_id: id } } }),
      ),
    moneyMoved,
  );
}

/** Direct link to the bill's PDF (the browser sends the session cookie, so this is not a hand-written API call). */
export function billPdfUrl(id: string, paper: "a4" | "thermal", lang: string): string {
  const base = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
  return `${base}/api/w/bills/${id}/pdf?format=${paper}&lang=${lang === "ta" ? "ta" : "en"}`;
}

/* ---- buying ----------------------------------------------------------------------------------------- */

export function usePurchases(filters: { q?: string; date_from?: string; date_to?: string }) {
  return useQuery({
    queryKey: [...queryKeys.purchases, "list", filters],
    queryFn: async () => unwrap(await api.GET("/api/w/purchases", { params: { query: { ...filters, limit: 100 } } })),
  });
}

export function usePurchase(id: string) {
  return useQuery({
    queryKey: [...queryKeys.purchases, "detail", id],
    queryFn: async () => unwrap(await api.GET("/api/w/purchases/{purchase_id}", { params: { path: { purchase_id: id } } })),
  });
}

export function useCreatePurchase() {
  return useWrite(
    async (body: Schemas["PurchaseIn"], key) =>
      unwrap(await api.POST("/api/w/purchases", { body, params: idemHeader(key) })),
    [queryKeys.purchases, ...moneyMoved],
  );
}

export function useVoidPurchase(id: string) {
  return useWrite(
    async (reason: string, key) =>
      unwrap(
        await api.POST("/api/w/purchases/{purchase_id}/void", {
          body: { reason },
          params: { ...idemHeader(key), path: { purchase_id: id } },
        }),
      ),
    [queryKeys.purchases, ...moneyMoved],
  );
}

/* ---- money ------------------------------------------------------------------------------------------ */

export function usePayments() {
  return useQuery({
    queryKey: queryKeys.payments,
    queryFn: async () => unwrap(await api.GET("/api/w/money/payments", { params: { query: { limit: 100 } } })),
  });
}

export function useCreatePayment() {
  return useWrite(
    async (body: Schemas["PaymentIn"], key) =>
      unwrap(await api.POST("/api/w/money/payments", { body, params: idemHeader(key) })),
    moneyMoved,
  );
}

export function useReversePayment() {
  return useWrite(
    async ({ paymentId, reason }: { paymentId: string; reason: string }, key) =>
      unwrap(
        await api.POST("/api/w/money/payments/{payment_id}/reverse", {
          body: { reason },
          params: { ...idemHeader(key), path: { payment_id: paymentId } },
        }),
      ),
    moneyMoved,
  );
}

/* ---- reports ---------------------------------------------------------------------------------------- */

export function useDayBook(day: string) {
  return useQuery({
    queryKey: [...queryKeys.reports, "daybook", day],
    queryFn: async () => unwrap(await api.GET("/api/w/reports/daybook", { params: { query: { date: day } } })),
  });
}

export function useSalesReport(from: string, to: string) {
  return useQuery({
    queryKey: [...queryKeys.reports, "sales", from, to],
    queryFn: async () => unwrap(await api.GET("/api/w/reports/sales", { params: { query: { from, to } } })),
  });
}

export function useGstReport(from: string, to: string) {
  return useQuery({
    queryKey: [...queryKeys.reports, "gst", from, to],
    queryFn: async () => unwrap(await api.GET("/api/w/reports/gst", { params: { query: { from, to } } })),
  });
}

export function useOutstandingReport() {
  return useQuery({
    queryKey: [...queryKeys.reports, "outstanding"],
    queryFn: async () => unwrap(await api.GET("/api/w/reports/outstanding")),
  });
}

export function useWastageReport(from: string, to: string) {
  return useQuery({
    queryKey: [...queryKeys.reports, "wastage", from, to],
    queryFn: async () => unwrap(await api.GET("/api/w/reports/wastage", { params: { query: { from, to } } })),
  });
}

/* ---- subscriptions ------------------------------------------------------------------------------------ */

export function useAdminPlans(includeInactive = true) {
  return useQuery({
    queryKey: [...queryKeys.adminPlans, includeInactive],
    queryFn: async () => unwrap(await api.GET("/api/admin/plans", { params: { query: { include_inactive: includeInactive } } })),
  });
}

export function useAdminCreatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["PlanCreate"]) => unwrap(await api.POST("/api/admin/plans", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminPlans }),
  });
}

export function useAdminUpdatePlan(key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["PlanUpdate"]) =>
      unwrap(await api.PATCH("/api/admin/plans/{key}", { body, params: { path: { key } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminPlans }),
  });
}

export type SubscriptionStatus = Schemas["SubscriptionOut"]["status"];

export function useAdminSubscriptions(status?: SubscriptionStatus) {
  return useQuery({
    queryKey: [...queryKeys.adminSubscriptions, "list", status ?? "all"],
    queryFn: async () => unwrap(await api.GET("/api/admin/subscriptions", { params: { query: { status } } })),
  });
}

export function useAdminSubscriptionStats() {
  return useQuery({
    queryKey: [...queryKeys.adminSubscriptions, "stats"],
    queryFn: async () => unwrap(await api.GET("/api/admin/subscriptions/stats")),
  });
}

export function useAdminSubscription(businessId: string) {
  return useQuery({
    queryKey: [...queryKeys.adminSubscriptions, "business", businessId],
    queryFn: async () =>
      unwrap(await api.GET("/api/admin/businesses/{business_id}/subscription", { params: { path: { business_id: businessId } } })),
  });
}

export function useAdminUpdateSubscription(businessId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["SubscriptionUpdate"]) =>
      unwrap(
        await api.PATCH("/api/admin/businesses/{business_id}/subscription", {
          body,
          params: { path: { business_id: businessId } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.adminSubscriptions });
    },
  });
}

/* ---- platform settings ---------------------------------------------------------------------------------- */

export function useAdminPlatformSettings() {
  return useQuery({
    queryKey: queryKeys.adminSettings,
    queryFn: async () => unwrap(await api.GET("/api/admin/settings")),
  });
}

export function useAdminUpdatePlatformSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["PlatformSettingsUpdate"]) =>
      unwrap(await api.PATCH("/api/admin/settings", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.adminSettings }),
  });
}
