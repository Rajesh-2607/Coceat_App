/** Calendar days as the trader sees them: India time, ISO 'YYYY-MM-DD' (what the API's date fields use). */

export function todayIst(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

export function monthStartIst(): string {
  return `${todayIst().slice(0, 8)}01`;
}

/** Add whole days to an ISO date without touching time zones. */
export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y!, m! - 1, d! + days));
  return date.toISOString().slice(0, 10);
}
