import { and, desc, eq, isNotNull, sql } from "drizzle-orm";
import { db } from "./client";
import { itemMentions, items, redditPosts, spreadsheetRows, spreadsheets } from "./schema";

export type SortKey = "trending" | "newest" | "price";

export type ItemCardData = {
  id: number;
  titleEn: string | null;
  brand: string | null;
  category: string | null;
  priceCny: string | null;
  imageUrls: string[] | null;
  mentionCount: number;
  trendScore: number;
};

export type ItemDetail = ItemCardData & {
  descriptionEn: string | null;
  sellerRebuyRate: number | null;
  productUrl: string;
  platform: string;
  sellerName: string | null;
  mentions: {
    permalink: string | null;
    title: string | null;
    score: number | null;
    aiSummary: string | null;
  }[];
};

const mentionCount = sql<number>`count(${itemMentions.redditPostId})::int`;
const trendScore = sql<number>`(count(${itemMentions.redditPostId}) + coalesce(sum(${redditPosts.score}), 0))::int`;

export async function getItems(opts: {
  category?: string;
  brand?: string;
  sort?: SortKey;
}): Promise<ItemCardData[]> {
  const filters = [eq(items.status, "active")];
  if (opts.category) filters.push(eq(items.category, opts.category));
  if (opts.brand) filters.push(eq(items.brand, opts.brand));

  const orderBy =
    opts.sort === "newest"
      ? desc(items.createdAt)
      : opts.sort === "price"
        ? sql`${items.priceCny} asc nulls last`
        : desc(trendScore);

  return db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      mentionCount,
      trendScore,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(...filters))
    .groupBy(items.id)
    .orderBy(orderBy);
}

export async function getItemDetail(id: number): Promise<ItemDetail | null> {
  const [row] = await db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      descriptionEn: items.descriptionEn,
      sellerRebuyRate: items.sellerRebuyRate,
      productUrl: items.productUrl,
      platform: items.platform,
      sellerName: items.sellerName,
      mentionCount,
      trendScore,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(eq(items.id, id), eq(items.status, "active")))
    .groupBy(items.id);

  if (!row) return null;

  const mentions = await db
    .select({
      permalink: redditPosts.permalink,
      title: redditPosts.title,
      score: redditPosts.score,
      aiSummary: redditPosts.aiSummary,
    })
    .from(itemMentions)
    .innerJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(eq(itemMentions.itemId, id))
    .orderBy(desc(redditPosts.score));

  return { ...row, mentions };
}

export async function getFilterOptions(): Promise<{ brands: string[]; categories: string[] }> {
  const brands = await db
    .selectDistinct({ v: items.brand })
    .from(items)
    .where(
      and(
        eq(items.status, "active"),
        isNotNull(items.brand),
        // multi-item haul labels ("Multiple (AMIRI, ...)") are not brands
        sql`${items.brand} NOT ILIKE 'multiple%'`,
      ),
    );
  const categories = await db
    .selectDistinct({ v: items.category })
    .from(items)
    .where(and(eq(items.status, "active"), isNotNull(items.category)));
  return {
    brands: brands.map((r) => r.v!).sort(),
    categories: categories.map((r) => r.v!).sort(),
  };
}

const fuzzy = (col: unknown, q: string) =>
  sql`(${col} % ${q} OR ${col} ILIKE ${"%" + q + "%"})`;

export async function searchItems(
  q: string,
  opts: { category?: string; brand?: string },
): Promise<ItemCardData[]> {
  const filters = [eq(items.status, "active")];
  if (opts.category) filters.push(eq(items.category, opts.category));
  if (opts.brand) filters.push(eq(items.brand, opts.brand));
  filters.push(
    sql`(${fuzzy(items.titleEn, q)} OR ${fuzzy(items.brand, q)} OR ${items.titleZh} ILIKE ${"%" + q + "%"})`,
  );
  return db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      mentionCount,
      trendScore,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(...filters))
    .groupBy(items.id)
    .orderBy(sql`greatest(similarity(coalesce(${items.titleEn}, ''), ${q}), similarity(coalesce(${items.brand}, ''), ${q})) DESC`);
}

export type StagingCardData = {
  id: number;
  name: string | null;
  priceRaw: string | null;
  currency: string | null;
  imageUrl: string | null;
  productUrl: string;
  platform: string;
  sheetTitle: string | null;
};

export async function searchStagingRows(q: string): Promise<StagingCardData[]> {
  const rows = await db
    .select({
      id: spreadsheetRows.id,
      name: spreadsheetRows.name,
      priceRaw: spreadsheetRows.priceRaw,
      currency: spreadsheetRows.currency,
      imageUrl: spreadsheetRows.imageUrl,
      productUrl: spreadsheetRows.productUrl,
      platform: spreadsheetRows.platform,
      sheetTitle: spreadsheets.title,
    })
    .from(spreadsheetRows)
    .innerJoin(spreadsheets, eq(spreadsheets.id, spreadsheetRows.spreadsheetId))
    .where(
      and(
        sql`${spreadsheetRows.itemId} IS NULL`,
        isNotNull(spreadsheetRows.productUrl),
        fuzzy(spreadsheetRows.name, q),
      ),
    )
    .orderBy(sql`similarity(coalesce(${spreadsheetRows.name}, ''), ${q}) DESC`)
    .limit(12);
  return rows as StagingCardData[];
}

export async function flagRowsForPromotion(q: string): Promise<void> {
  await db.execute(sql`
    UPDATE spreadsheet_rows SET requested_at = now()
    WHERE id IN (
      SELECT id FROM spreadsheet_rows
      WHERE item_id IS NULL AND promote_error IS NULL AND product_url IS NOT NULL
        AND requested_at IS NULL
        AND (name % ${q} OR name ILIKE ${"%" + q + "%"})
      ORDER BY similarity(coalesce(name, ''), ${q}) DESC
      LIMIT 5
    )
  `);
}
