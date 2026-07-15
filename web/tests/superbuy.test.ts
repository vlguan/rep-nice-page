import { afterEach, describe, expect, it } from "vitest";
import { superbuyUrl } from "../src/lib/superbuy";
import { cnyToUsd } from "../src/lib/format";

afterEach(() => {
  delete process.env.SUPERBUY_PARTNER_CODE;
});

describe("superbuyUrl", () => {
  it("builds the platform/id form with partner code and tracking", () => {
    expect(superbuyUrl("https://weidian.com/item.html?itemID=7506689137", "wcOcdG")).toBe(
      "https://www.superbuy.com/en/page/buy/?platform=WD&id=7506689137&partnercode=wcOcdG&trackPayload=pc_share",
    );
  });

  it("omits partner params when no code is configured", () => {
    expect(superbuyUrl("https://weidian.com/item.html?itemID=123")).toBe(
      "https://www.superbuy.com/en/page/buy/?platform=WD&id=123",
    );
  });

  it("reads the partner code from SUPERBUY_PARTNER_CODE by default", () => {
    process.env.SUPERBUY_PARTNER_CODE = "wcOcdG";
    expect(superbuyUrl("https://weidian.com/item.html?itemID=123")).toBe(
      "https://www.superbuy.com/en/page/buy/?platform=WD&id=123&partnercode=wcOcdG&trackPayload=pc_share",
    );
  });

  it("falls back to the url wrapper when the item id cannot be parsed", () => {
    expect(superbuyUrl("https://weidian.com/some/other/page")).toBe(
      "https://www.superbuy.com/en/page/buy/?url=https%3A%2F%2Fweidian.com%2Fsome%2Fother%2Fpage",
    );
  });
});

describe("cnyToUsd", () => {
  it("converts with the fixed rate", () => {
    expect(cnyToUsd(100)).toBeCloseTo(14);
  });
});
