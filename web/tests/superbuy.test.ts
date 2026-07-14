import { describe, expect, it } from "vitest";
import { superbuyUrl } from "../src/lib/superbuy";
import { cnyToUsd } from "../src/lib/format";

describe("superbuyUrl", () => {
  it("wraps and encodes the weidian url", () => {
    expect(superbuyUrl("https://weidian.com/item.html?itemID=123")).toBe(
      "https://www.superbuy.com/en/page/buy/?url=https%3A%2F%2Fweidian.com%2Fitem.html%3FitemID%3D123",
    );
  });
});

describe("cnyToUsd", () => {
  it("converts with the fixed rate", () => {
    expect(cnyToUsd(100)).toBeCloseTo(14);
  });
});
