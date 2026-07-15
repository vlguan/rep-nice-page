import { and, desc, eq, isNotNull, sql } from "drizzle-orm";
import { db } from "./client";
import { itemMentions, items, redditPosts } from "./schema";

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
    .where(and(eq(items.status, "active"), isNotNull(items.brand)));
  const categories = await db
    .selectDistinct({ v: items.category })
    .from(items)
    .where(and(eq(items.status, "active"), isNotNull(items.category)));
  return {
    brands: brands.map((r) => r.v!).sort(),
    categories: categories.map((r) => r.v!).sort(),
  };
}
