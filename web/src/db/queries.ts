import { and, asc, desc, eq, inArray, isNotNull, ne, or, sql } from "drizzle-orm";
import { db } from "./client";
import { itemMentions, items, redditPosts, spreadsheetRows, spreadsheets, stores } from "./schema";

export type SortKey = "trending" | "newest" | "price";

export type ItemCardData = {
  id: number;
  titleEn: string | null;
  brand: string | null;
  category: string | null;
  priceCny: string | null;
  imageUrls: string[] | null;
  sold: number | null;
  mentionCount: number;
  trendScore: number;
};

export type ItemDetail = ItemCardData & {
  descriptionEn: string | null;
  style: string | null;
  sellerRebuyRate: number | null;
  productUrl: string;
  platform: string;
  sellerName: string | null;
  store: { userid: string; name: string | null; note: string | null } | null;
  mentions: {
    permalink: string | null;
    title: string | null;
    score: number | null;
    aiSummary: string | null;
    quote: string | null;
  }[];
};

const mentionCount = sql<number>`count(${itemMentions.redditPostId})::int`;
const trendScore = sql<number>`(count(${itemMentions.redditPostId}) + coalesce(sum(${redditPosts.score}), 0))::int`;
// total matching rows regardless of LIMIT (window runs before LIMIT is applied)
const totalCount = sql<number>`count(*) over()::int`;

export const PAGE_SIZE = 100;
export type Paginated<T> = { items: T[]; total: number };

export async function getItems(opts: {
  category?: string;
  brand?: string;
  style?: string;
  sort?: SortKey;
  shop?: string;
  page?: number;
}): Promise<Paginated<ItemCardData>> {
  const filters = [eq(items.status, "active")];
  if (opts.category) filters.push(eq(items.category, opts.category));
  if (opts.brand) filters.push(eq(items.brand, opts.brand));
  if (opts.style) filters.push(eq(items.style, opts.style));
  if (opts.shop) filters.push(eq(items.shopUserid, opts.shop));

  const orderBy =
    opts.sort === "newest"
      ? desc(items.createdAt)
      : opts.sort === "price"
        ? sql`${items.priceCny} asc nulls last`
        : desc(trendScore);

  const page = Math.max(1, opts.page ?? 1);
  const rows = await db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      sold: items.sold,
      mentionCount,
      trendScore,
      total: totalCount,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(...filters))
    .groupBy(items.id)
    .orderBy(orderBy)
    .limit(PAGE_SIZE)
    .offset((page - 1) * PAGE_SIZE);
  return { items: rows.map(({ total, ...r }) => r), total: rows[0]?.total ?? 0 };
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
      sold: items.sold,
      descriptionEn: items.descriptionEn,
      style: items.style,
      sellerRebuyRate: items.sellerRebuyRate,
      productUrl: items.productUrl,
      platform: items.platform,
      sellerName: items.sellerName,
      shopUserid: items.shopUserid,
      mentionCount,
      trendScore,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(eq(items.id, id), eq(items.status, "active")))
    .groupBy(items.id);

  if (!row) return null;

  const { shopUserid, ...rest } = row;
  let store: ItemDetail["store"] = null;
  if (shopUserid) {
    const [s] = await db
      .select({ userid: stores.userid, name: stores.name, note: stores.note })
      .from(stores)
      .where(eq(stores.userid, shopUserid));
    store = s ?? null;
  }

  const mentions = await db
    .select({
      permalink: redditPosts.permalink,
      title: redditPosts.title,
      score: redditPosts.score,
      aiSummary: redditPosts.aiSummary,
      quote: itemMentions.quote,
    })
    .from(itemMentions)
    .innerJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(eq(itemMentions.itemId, id))
    .orderBy(desc(redditPosts.score));

  return { ...rest, store, mentions };
}

export type StoreRow = {
  userid: string;
  name: string | null;
  note: string | null;
  itemCount: number;
  rebuyRate: number | null;
};

/**
 * Recommend items matching the user's viewed styles/brands — one standout item
 * per category (DISTINCT ON), ranked by brand match, then style match, then
 * popularity. Returns [] when there's no taste signal.
 */
export async function getRecommendations(opts: {
  styles: string[];
  brands: string[];
  excludeId?: number;
}): Promise<ItemCardData[]> {
  const { styles, brands, excludeId } = opts;
  if (styles.length === 0 && brands.length === 0) return [];

  const brandMatch = brands.length ? inArray(items.brand, brands) : sql`false`;
  const styleMatch = styles.length ? inArray(items.style, styles) : sql`false`;
  const score = sql<number>`((case when ${brandMatch} then 2 else 0 end) + (case when ${styleMatch} then 1 else 0 end))`;

  const conds = [eq(items.status, "active"), isNotNull(items.category), or(brandMatch, styleMatch)];
  if (excludeId) conds.push(ne(items.id, excludeId));

  return db
    .selectDistinctOn([items.category], {
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      sold: items.sold,
      mentionCount: sql<number>`0`,
      trendScore: sql<number>`0`,
    })
    .from(items)
    .where(and(...conds))
    .orderBy(items.category, desc(score), sql`${items.sold} desc nulls last`, desc(items.id));
}

export type StoreSort = "rate" | "items" | "name";

export async function getStores(opts: { q?: string; sort?: StoreSort } = {}): Promise<StoreRow[]> {
  const conds = [];
  if (opts.q) {
    const like = `%${opts.q}%`;
    conds.push(sql`(${stores.name} ILIKE ${like} OR ${stores.note} ILIKE ${like})`);
  }
  const orderBy =
    opts.sort === "items"
      ? desc(sql`count(${items.id})`)
      : opts.sort === "name"
        ? asc(stores.name)
        : sql`avg(${items.sellerRebuyRate}) desc nulls last`; // default: highest repeat first

  return db
    .select({
      userid: stores.userid,
      name: stores.name,
      note: stores.note,
      itemCount: sql<number>`count(${items.id})::int`,
      rebuyRate: sql<number>`round(avg(${items.sellerRebuyRate}))::int`,
    })
    .from(stores)
    .leftJoin(items, and(eq(items.shopUserid, stores.userid), eq(items.status, "active")))
    .where(conds.length ? and(...conds) : undefined)
    .groupBy(stores.userid, stores.name, stores.note)
    .having(sql`count(${items.id}) > 0`)
    .orderBy(orderBy);
}

export async function getFilterOptions(): Promise<{ brands: string[]; categories: string[]; styles: string[] }> {
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
  const styles = await db
    .selectDistinct({ v: items.style })
    .from(items)
    .where(and(eq(items.status, "active"), isNotNull(items.style)));
  return {
    brands: brands.map((r) => r.v!).sort(),
    categories: categories.map((r) => r.v!).sort(),
    styles: styles.map((r) => r.v!).sort(),
  };
}

const fuzzy = (col: unknown, q: string) =>
  sql`(${col} % ${q} OR ${col} ILIKE ${"%" + q + "%"})`;

export async function searchItems(
  q: string,
  opts: { category?: string; brand?: string; page?: number },
): Promise<Paginated<ItemCardData>> {
  const filters = [eq(items.status, "active")];
  if (opts.category) filters.push(eq(items.category, opts.category));
  if (opts.brand) filters.push(eq(items.brand, opts.brand));
  filters.push(
    sql`(${fuzzy(items.titleEn, q)} OR ${fuzzy(items.brand, q)} OR ${items.titleZh} ILIKE ${"%" + q + "%"})`,
  );
  const page = Math.max(1, opts.page ?? 1);
  const rows = await db
    .select({
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      sold: items.sold,
      mentionCount,
      trendScore,
      total: totalCount,
    })
    .from(items)
    .leftJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .leftJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(and(...filters))
    .groupBy(items.id)
    .orderBy(sql`greatest(similarity(coalesce(${items.titleEn}, ''), ${q}), similarity(coalesce(${items.brand}, ''), ${q})) DESC`)
    .limit(PAGE_SIZE)
    .offset((page - 1) * PAGE_SIZE);
  return { items: rows.map(({ total, ...r }) => r), total: rows[0]?.total ?? 0 };
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
