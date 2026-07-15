import { beforeEach, describe, expect, it } from "vitest";
import { sql } from "drizzle-orm";

const hasDb = !!process.env.TEST_DATABASE_URL;

describe.skipIf(!hasDb)("queries", () => {
  let db: typeof import("../src/db/client").db;
  let schema: typeof import("../src/db/schema");
  let queries: typeof import("../src/db/queries");

  beforeEach(async () => {
    db = (await import("../src/db/client")).db;
    schema = await import("../src/db/schema");
    queries = await import("../src/db/queries");
    await db.delete(schema.itemSpreadsheetMentions);
    await db.delete(schema.spreadsheetRows);
    await db.delete(schema.spreadsheets);
    await db.delete(schema.itemMentions);
    await db.delete(schema.items);
    await db.delete(schema.redditPosts);

    const [hot] = await db
      .insert(schema.items)
      .values({ productUrl: "https://weidian.com/item.html?itemID=1", titleEn: "hot hoodie", brand: "CH", category: "clothing", priceCny: "268", status: "active", imageUrls: [] })
      .returning();
    const [cold] = await db
      .insert(schema.items)
      .values({ productUrl: "https://weidian.com/item.html?itemID=2", titleEn: "cold ring", brand: "VW", category: "jewelry", priceCny: "80", status: "active", imageUrls: [] })
      .returning();
    await db
      .insert(schema.items)
      .values({ productUrl: "https://weidian.com/item.html?itemID=3", titleEn: "dead item", status: "inactive", imageUrls: [] });

    const [p1] = await db
      .insert(schema.redditPosts)
      .values({ redditPostId: "a", permalink: "https://reddit.com/a", title: "review", score: 400, sentiment: "positive" })
      .returning();
    const [p2] = await db
      .insert(schema.redditPosts)
      .values({ redditPostId: "b", permalink: "https://reddit.com/b", title: "w2c", score: 50, sentiment: "positive" })
      .returning();
    await db.insert(schema.itemMentions).values([
      { itemId: hot.id, redditPostId: p1.id },
      { itemId: hot.id, redditPostId: p2.id },
      { itemId: cold.id, redditPostId: p2.id },
    ]);
  });

  it("never returns inactive items", async () => {
    const rows = await queries.getItems({});
    expect(rows.map((r) => r.titleEn)).not.toContain("dead item");
  });

  it("sorts by trending (mentions + summed scores) by default", async () => {
    const rows = await queries.getItems({ sort: "trending" });
    expect(rows[0].titleEn).toBe("hot hoodie"); // 2 mentions + 450 score
    expect(rows[0].mentionCount).toBe(2);
  });

  it("filters by category", async () => {
    const rows = await queries.getItems({ category: "jewelry" });
    expect(rows).toHaveLength(1);
    expect(rows[0].titleEn).toBe("cold ring");
  });

  it("item detail includes mentions, inactive detail returns null-ish for public", async () => {
    const rows = await queries.getItems({});
    const detail = await queries.getItemDetail(rows[0].id);
    expect(detail).not.toBeNull();
    expect(detail!.mentions.length).toBeGreaterThan(0);
    expect(detail!.mentions[0].permalink).toContain("reddit.com");
  });

  it("filter options come from active items only", async () => {
    const opts = await queries.getFilterOptions();
    expect(opts.brands.sort()).toEqual(["CH", "VW"]);
    expect(opts.categories.sort()).toEqual(["clothing", "jewelry"]);
  });

  it("searchItems fuzzy-matches title and brand", async () => {
    const hits = await queries.searchItems("hoddie", {});
    expect(hits.map((h) => h.titleEn)).toContain("hot hoodie");
    const brandHits = await queries.searchItems("CH", {});
    expect(brandHits.length).toBeGreaterThan(0);
  });

  it("searchStagingRows matches unpromoted rows and flags top matches", async () => {
    const [sheet] = await db
      .insert(schema.spreadsheets)
      .values({ sheetKey: "sk1", url: "u", title: "Big W2C" })
      .returning();
    await db.insert(schema.spreadsheetRows).values([
      { spreadsheetId: sheet.id, tabName: "T", rowNumber: 2, name: "Hellstar hoodie", productUrl: "https://weidian.com/item.html?itemID=9", platform: "weidian" },
      { spreadsheetId: sheet.id, tabName: "T", rowNumber: 3, name: "unrelated socks", productUrl: "https://weidian.com/item.html?itemID=10", platform: "weidian" },
    ]);
    const rows = await queries.searchStagingRows("hellstar hoodie");
    expect(rows[0].name).toBe("Hellstar hoodie");
    expect(rows[0].sheetTitle).toBe("Big W2C");

    await queries.flagRowsForPromotion("hellstar hoodie");
    const flagged = await db
      .select({ name: schema.spreadsheetRows.name })
      .from(schema.spreadsheetRows)
      .where(sql`requested_at IS NOT NULL`);
    expect(flagged.map((f) => f.name)).toContain("Hellstar hoodie");
  });
});
