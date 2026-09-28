import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { Schemas } from "../../api/client";
import i18n from "../../i18n";
import { LocationProvider } from "../location";
import { SellPage } from "./SellPage";

const now = "2026-09-28T04:00:00Z";
const banana = {
  id: "p1", name: "Banana", name_ta: null, kind: "weight", unit_id: "u-kg", default_price_paise: 4500,
  gst_rate_bp: 0, hsn_code: null, is_active: true, varieties: [], created_at: now, updated_at: now,
};
const kg = { id: "u-kg", code: "kg", name: "Kilogram", name_ta: null, kind: "weight", base_factor: 1000, is_active: true };
const shop = { id: "l1", name: "Shop", name_ta: null, kind: "shop", is_active: true, created_at: now, updated_at: now };
const balance = {
  location_id: "l1", product_id: "p1", variety_id: null, grade_id: null, quantity: 87_500, kind: "weight",
  product_name: "Banana", product_name_ta: null, variety_name: null, variety_name_ta: null, grade_name: null, grade_name_ta: null,
};
const context = {
  business: { id: "b1", name: "ABC", name_ta: null, gstin: null, address: null, phone: null, vertical_key: "banana", enabled_modules: ["sell"], status: "active", created_at: now },
  role: "owner", location_ids: null, permissions: ["bills.create"],
} as Schemas["WorkspaceContextOut"];

const data: Record<string, unknown> = {
  "/api/w/products": [banana],
  "/api/w/units": [kg],
  "/api/w/grades": [],
  "/api/w/customers": [],
  "/api/w/locations": [shop],
  "/api/w/stock/balances": [balance],
};

function mountSell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/w/sell"]}>
        <LocationProvider businessId="b1">
          <Routes>
            <Route path="/w/sell" element={<SellPage context={context} />} />
            <Route path="/w/bills/:id" element={<p>Bill page</p>} />
          </Routes>
        </LocationProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function addBanana(kgText: string) {
  await screen.findByRole("option", { name: "Banana" }); // the product list has loaded
  fireEvent.change(screen.getByLabelText("Product"), { target: { value: "p1" } });
  fireEvent.change(screen.getByLabelText(/^Quantity/), { target: { value: kgText } });
  fireEvent.click(screen.getByRole("button", { name: /Add to bill/ }));
}

const postKey = (call: unknown[]) => (call[1] as { params: { header: Record<string, string> } }).params.header["Idempotency-Key"];

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.spyOn(api, "GET").mockImplementation((async (url: string) => ({
    data: data[url] ?? [],
    response: new Response(null, { status: 200 }),
  })) as never);
});
afterEach(() => vi.restoreAllMocks());

describe("Sell page", () => {
  it("shows the exact total with round-off and sends a cash-in-full bill", async () => {
    const post = vi.spyOn(api, "POST").mockResolvedValue({
      data: { id: "bill-1" },
      response: new Response(null, { status: 201 }),
    } as never);
    mountSell();
    await addBanana("12.5");

    // 12.5 kg at Rs 45 = Rs 562.50; the bill is rounded up to Rs 563 and the round-off is shown
    expect(await screen.findByText("Round off")).toBeInTheDocument();
    expect(screen.getByText("+₹0.5")).toBeInTheDocument();
    expect(screen.getByText("✓ Paid in full")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Make bill · ₹563/ }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, init] = post.mock.calls[0] as unknown as [string, { body: Schemas["SaleIn"] }];
    expect(url).toBe("/api/w/bills");
    expect(init.body).toMatchObject({
      location_id: "l1",
      party_id: null,
      lines: [{ product_id: "p1", unit_id: "u-kg", quantity: 12_500, unit_price_paise: 4_500 }],
      payments: [{ method: "cash", amount_paise: 56_300 }],
    });
    expect(await screen.findByText("Bill page")).toBeInTheDocument();
  });

  it("refuses a credit sale to a walk-in customer", async () => {
    mountSell();
    await addBanana("2");
    const pay = screen.getByRole("heading", { name: "How was it paid?" }).parentElement!;
    fireEvent.click(within(pay).getByRole("button", { name: "All on credit" }));
    expect(await screen.findByText("Choose a customer to sell on credit.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Make bill/ })).toBeDisabled();
  });

  it("reuses one idempotency key when the same bill is sent again, and a new one after the bill changes", async () => {
    const post = vi.spyOn(api, "POST").mockResolvedValue({
      error: { code: "insufficient_stock" },
      response: new Response(null, { status: 422 }),
    } as never);
    mountSell();
    await addBanana("2");
    const make = () => screen.getByRole("button", { name: /Make bill/ });
    fireEvent.click(make());
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Not enough stock at this location.")).toBeInTheDocument();
    fireEvent.click(make());
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(postKey(post.mock.calls[1]!)).toBe(postKey(post.mock.calls[0]!)); // same bill, same key

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await addBanana("3");
    fireEvent.click(make());
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect(postKey(post.mock.calls[2]!)).not.toBe(postKey(post.mock.calls[0]!)); // a different bill
  });
});
