import { describe, expect, it } from "vitest";
import { reviewBullets } from "../src/lib/format";

describe("reviewBullets", () => {
  it("returns [] for empty input", () => {
    expect(reviewBullets(null)).toEqual([]);
    expect(reviewBullets("")).toEqual([]);
  });

  it("strips purchase URLs and label-only lines, keeps commentary", () => {
    const quote = "W2C:\nGraphics are bold but not overdone\nhttps://weidian.com/item.html?itemID=7739275528";
    expect(reviewBullets(quote)).toEqual(["Graphics are bold but not overdone"]);
  });

  it("splits multi-line quotes into bullets and dedupes", () => {
    const quote = "Fits slightly loose, TTS is fine\n8/10\nfits slightly loose, tts is fine";
    expect(reviewBullets(quote)).toEqual(["Fits slightly loose, TTS is fine", "8/10"]);
  });

  it("drops a line that was only a link", () => {
    expect(reviewBullets("https://cnfans.com/product/?id=1 weidian.com/item/2")).toEqual([]);
  });
});
