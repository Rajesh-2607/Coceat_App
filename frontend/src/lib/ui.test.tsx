import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import i18n from "../i18n";
import { ErrorText } from "./ui";

describe("ErrorText", () => {
  it("translates API error codes", async () => {
    await i18n.changeLanguage("en");
    render(<ErrorText error={new ApiError(403, "module_disabled")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This section is not enabled for your business.");
  });

  it("falls back to a generic message for unknown codes", async () => {
    await i18n.changeLanguage("ta");
    render(<ErrorText error={new ApiError(500, "brand_new_code")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("ஏதோ தவறு நடந்தது");
  });
});
