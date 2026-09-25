import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, newIdempotencyKey, unwrap, type Schemas } from "./client";

/** Retry only network failures and 5xx; a 4xx (validation, conflict, permission) will not change on retry. */
function retryTransient(failureCount: number, error: unknown): boolean {
  return failureCount < 3 && !(error instanceof ApiError && error.status < 500);
}

export const queryKeys = {
  me: ["me"] as const,
  context: ["w", "context"] as const,
  locations: ["w", "locations"] as const,
};

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

export function useLocations() {
  return useQuery({
    queryKey: queryKeys.locations,
    queryFn: async () => unwrap(await api.GET("/api/w/locations")),
  });
}

export function useCreateLocation() {
  const qc = useQueryClient();
  return useMutation({
    // the key travels in the variables, so TanStack's automatic retries reuse it
    mutationFn: async ({ body, key }: { body: Schemas["LocationCreate"]; key: string }) =>
      unwrap(await api.POST("/api/w/locations", { body, params: { header: { "Idempotency-Key": key } } })),
    retry: retryTransient,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.locations }),
  });
}

export { newIdempotencyKey };
