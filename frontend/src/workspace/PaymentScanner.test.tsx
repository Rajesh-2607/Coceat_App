import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { PaymentRows, type PayRow } from "./PaymentRows";

function renderRows(rows: PayRow[]) {
  return render(<PaymentRows rows={rows} onChange={() => {}} total={0} />);
}

describe("payment scanner", () => {
  it("shows the UPI scanner when a row is paid by UPI", async () => {
    await i18n.changeLanguage("en");
    renderRows([{ method: "upi", amount: "" }]);
    expect(screen.getByRole("img", { name: "UPI payment scanner" })).toHaveAttribute("src", "/payment-scanner.svg");
  });

  it("hides the scanner for cash-only payments", async () => {
    await i18n.changeLanguage("en");
    renderRows([{ method: "cash", amount: "" }]);
    expect(screen.queryByRole("img", { name: "UPI payment scanner" })).toBeNull();
  });
});
