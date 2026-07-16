import { describe, expect, it } from "vitest";
import { reviewQuote } from "../src/lib/format";

describe("reviewQuote", () => {
  it("returns null for empty input", () => {
    expect(reviewQuote(null)).toBeNull();
    expect(reviewQuote("")).toBeNull();
  });

  it("strips purchase URLs and label-only lines", () => {
    const quote = "W2C:\nGraphics are bold but not overdone\nhttps://weidian.com/item.html?itemID=7739275528";
    expect(reviewQuote(quote)).toBe("Graphics are bold but not overdone");
  });

  it("drops the enumeration label and keeps one continuous review", () => {
    const quote =
      "7. Stüssy Thermal (Size M)\nThe Stüssy thermal has always been my favourite, feels a bit bigger\nhttps://weidian.com/item/1";
    expect(reviewQuote(quote)).toBe(
      "The Stüssy thermal has always been my favourite, feels a bit bigger",
    );
  });

  it("joins a multi-line review into a single continuous string", () => {
    expect(reviewQuote("Fits slightly loose, TTS is fine\n8/10")).toBe("Fits slightly loose, TTS is fine 8/10");
  });

  it("returns null when only a link remains", () => {
    expect(reviewQuote("https://cnfans.com/product/?id=1 weidian.com/item/2")).toBeNull();
  });
});
