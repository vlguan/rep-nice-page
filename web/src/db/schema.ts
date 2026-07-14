import {
  pgTable, serial, text, integer, numeric, jsonb, timestamp, primaryKey,
} from "drizzle-orm/pg-core";

export const items = pgTable("items", {
  id: serial("id").primaryKey(),
  weidianUrl: text("weidian_url").notNull().unique(),
  weidianItemId: text("weidian_item_id"),
  titleZh: text("title_zh"),
  titleEn: text("title_en"),
  descriptionEn: text("description_en"),
  brand: text("brand"),
  category: text("category"), // clothing | jewelry | shoes | accessory
  priceCny: numeric("price_cny"),
  sellerName: text("seller_name"),
  imageUrls: jsonb("image_urls").$type<string[]>(),
  status: text("status").notNull().default("active"), // active | inactive
  lastValidatedAt: timestamp("last_validated_at", { withTimezone: true }),
  deadSince: timestamp("dead_since", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

export const redditPosts = pgTable("reddit_posts", {
  id: serial("id").primaryKey(),
  redditPostId: text("reddit_post_id").notNull().unique(),
  permalink: text("permalink"),
  title: text("title"),
  subreddit: text("subreddit"),
  score: integer("score"),
  numComments: integer("num_comments"),
  postedAt: timestamp("posted_at", { withTimezone: true }),
  scrapedAt: timestamp("scraped_at", { withTimezone: true }),
  sentiment: text("sentiment"), // positive | negative | flagged | null (no weidian link)
  aiSummary: text("ai_summary"),
});

export const itemMentions = pgTable(
  "item_mentions",
  {
    itemId: integer("item_id").notNull().references(() => items.id),
    redditPostId: integer("reddit_post_id").notNull().references(() => redditPosts.id),
  },
  (t) => [primaryKey({ columns: [t.itemId, t.redditPostId] })],
);

export const scrapeRuns = pgTable("scrape_runs", {
  id: serial("id").primaryKey(),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
  postsSeen: integer("posts_seen"),
  itemsAdded: integer("items_added"),
  itemsDeactivated: integer("items_deactivated"),
  error: text("error"),
});
