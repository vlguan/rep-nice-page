import { and, asc, desc, eq, inArray, isNotNull, notInArray, or, sql } from "drizzle-orm";
import { db } from "./client";
import { itemMentions, items, redditPosts, spreadsheetRows, spreadsheets, stores } from "./schema";

export type SortKey = "trending" | "newest" | "price" | "value";

// Recency window for the dedicated /trending page: only mentions from Reddit
// posts newer than this count toward "what's hot right now". Tunable — kept
// generous because the Reddit scrape runs weekly.
const TRENDING_WINDOW_DAYS = 45;

// "Best value" ranking: proven demand (rebuy rate × sales) per yuan. Null-guarded
// so items missing price/sold/rebuy sink to the bottom rather than erroring.
const valueScore = sql`(coalesce(${items.sellerRebuyRate}, 0) * ln(coalesce(${items.sold}, 0) + 1) / nullif(${items.priceCny}, 0))`;

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
        : opts.sort === "value"
          ? sql`${valueScore} desc nulls last`
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

/**
 * "Trending" — items whose Reddit buzz is recent, not all-time. Only mentions
 * from posts within TRENDING_WINDOW_DAYS count, so a once-viral item from months
 * ago drops off. Ranked by recent trend score (mentions + recent post score).
 */
export async function getTrending(opts: { page?: number } = {}): Promise<Paginated<ItemCardData>> {
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
    // inner join semantics: the postedAt filter drops items with no recent mention
    .innerJoin(itemMentions, eq(itemMentions.itemId, items.id))
    .innerJoin(redditPosts, eq(redditPosts.id, itemMentions.redditPostId))
    .where(
      and(
        eq(items.status, "active"),
        sql`${redditPosts.postedAt} > now() - (${TRENDING_WINDOW_DAYS} * interval '1 day')`,
      ),
    )
    .groupBy(items.id)
    .orderBy(desc(trendScore))
    .limit(PAGE_SIZE)
    .offset((page - 1) * PAGE_SIZE);
  return { items: rows.map(({ total, ...r }) => r), total: rows[0]?.total ?? 0 };
}

/**
 * "Slept on" — proven but unhyped. A seller rebuy rate in the top 30% (percentile
 * computed live, so it self-tunes) plus real sales, but zero Reddit mentions:
 * the source data says people keep buying, the community just hasn't caught on.
 */
export async function getSleptOn(opts: { page?: number } = {}): Promise<Paginated<ItemCardData>> {
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
      mentionCount: sql<number>`0`,
      trendScore: sql<number>`0`,
      total: totalCount,
    })
    .from(items)
    .where(
      and(
        eq(items.status, "active"),
        isNotNull(items.sellerRebuyRate),
        sql`${items.sellerRebuyRate} >= (
          SELECT percentile_cont(0.7) WITHIN GROUP (ORDER BY seller_rebuy_rate)
          FROM items WHERE status = 'active' AND seller_rebuy_rate IS NOT NULL
        )`,
        sql`coalesce(${items.sold}, 0) >= 20`,
        sql`NOT EXISTS (SELECT 1 FROM item_mentions WHERE item_id = ${items.id})`,
      ),
    )
    .orderBy(desc(items.sellerRebuyRate), sql`${items.sold} desc nulls last`)
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
 * Recommend items matching the user's viewed styles/brands. Picks one standout
 * per (category, style) so a mixed taste blends across the top styles, ranked
 * by brand match, then style match, then popularity — capped to a tidy row.
 * Returns [] when there's no taste signal.
 */
export async function getRecommendations(opts: {
  styles: string[];
  brands: string[];
  excludeIds?: number[];
  limit?: number;
}): Promise<ItemCardData[]> {
  const { styles, brands, excludeIds, limit = 8 } = opts;
  if (styles.length === 0 && brands.length === 0) return [];

  const brandMatch = brands.length ? inArray(items.brand, brands) : sql`false`;
  const styleMatch = styles.length ? inArray(items.style, styles) : sql`false`;
  const score = sql<number>`((case when ${brandMatch} then 2 else 0 end) + (case when ${styleMatch} then 1 else 0 end))`;

  const conds = [eq(items.status, "active"), isNotNull(items.category), or(brandMatch, styleMatch)];
  if (excludeIds?.length) conds.push(notInArray(items.id, excludeIds));

  const rows = await db
    .selectDistinctOn([items.category, items.style], {
      id: items.id,
      titleEn: items.titleEn,
      brand: items.brand,
      category: items.category,
      priceCny: items.priceCny,
      imageUrls: items.imageUrls,
      sold: items.sold,
      mentionCount: sql<number>`0`,
      trendScore: sql<number>`0`,
      _score: score,
    })
    .from(items)
    .where(and(...conds))
    .orderBy(items.category, items.style, desc(score), sql`${items.sold} desc nulls last`, desc(items.id));

  // one row per (category, style); rank the blend and keep a tidy top slice.
  return rows
    .sort((a, b) => b._score - a._score || (b.sold ?? 0) - (a.sold ?? 0))
    .slice(0, limit)
    .map(({ _score, ...r }) => r);
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
