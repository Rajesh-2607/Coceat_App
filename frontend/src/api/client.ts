import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL,
  credentials: "include", // httpOnly session cookie; the token is never readable by JS
});

/** Error body returned by the API for domain errors: `code` is translated via i18n `errors.<code>`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Unwrap an openapi-fetch result or throw ApiError (so TanStack Query sees failures). */
export function unwrap<T>({ data, error, response }: Result<T>): T {
  if (error !== undefined || !response.ok) {
    const code =
      typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
        ? error.code
        : response.status === 422
          ? "validation"
          : "unknown";
    throw new ApiError(response.status, code);
  }
  return data as T;
}

/**
 * One key per user action, created when the action starts (not per HTTP attempt), so every retry
 * of the same sale/payment carries the same key and the server never records it twice.
 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID().replaceAll("-", "");
}
