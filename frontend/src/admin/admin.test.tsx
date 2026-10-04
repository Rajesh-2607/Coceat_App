import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import i18n from "../i18n";
import { AdminApp } from "./AdminApp";

const business = {
  id: "b1",
  name: "ABC Banana Traders",
  name_ta: null,
  gstin: null,
  vertical_key: "banana",
  enabled_modules: ["stock", "customers"],
  status: "active",
  created_at: "2026-09-28T04:00:00Z",
};
const me = { id: "u1", name: "Admin", name_ta: null, language: "en", is_platform_admin: true, current_business_id: null, memberships: [] };

afterEach(() => vi.restoreAllMocks());

describe("AdminApp", () => {
  it("renders the overview with the businesses list", async () => {
    await i18n.changeLanguage("en");
    vi.spyOn(api, "GET").mockImplementation((async (url: string) => ({
      data: url === "/api/me" ? me : [business],
      response: new Response(null, { status: 200 }),
    })) as never);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/admin"]}>
          <Routes>
            <Route path="/admin/*" element={<AdminApp />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Cocreat Platform")).toBeInTheDocument();
    expect(await screen.findByText("ABC Banana Traders")).toBeInTheDocument();
    expect(screen.getByText("Total businesses")).toBeInTheDocument();
  });
});
