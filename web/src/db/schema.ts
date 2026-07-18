import {
  pgTable, serial, text, integer, numeric, jsonb, timestamp, primaryKey, unique,
} from "drizzle-orm/pg-core";

export const items = pgTable("items", {
  id: serial("id").primaryKey(),
  productUrl: text("product_url").notNull().unique(),
  platformItemId: text("platform_item_id"),
  platform: text("platform").notNull().default("weidian"), // weidian | taobao
  titleZh: text("title_zh"),
  titleEn: text("title_en"),
  descriptionEn: text("description_en"),
  brand: text("brand"),
  category: text("category"), // clothing | jewelry | shoes | accessory | luggage
  style: text("style"), // gorpcore | hypebeast | athleisure | old money | luxury | minimalist | alt | opium | goth
  priceCny: numeric("price_cny"),
  sellerName: text("seller_name"),
  sellerRebuyRate: integer("seller_rebuy_rate"), // % of shop's buyers who buy again
  sold: integer("sold"), // units sold (from Weidian shop item list; store-seeded items)
  shopUserid: text("shop_userid"), // Weidian shop this item came from (-> stores.userid)
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
    quote: text("quote"), // verbatim Reddit text that mentioned this item
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
  kind: text("kind").default("reddit"), // reddit | store
});

export const spreadsheets = pgTable("spreadsheets", {
  id: serial("id").primaryKey(),
  sheetKey: text("sheet_key").notNull().unique(),
  url: text("url").notNull(),
  title: text("title"),
  discoveredPostId: integer("discovered_post_id").references(() => redditPosts.id),
  discoveredAt: timestamp("discovered_at", { withTimezone: true }).defaultNow(),
  lastSyncedAt: timestamp("last_synced_at", { withTimezone: true }),
  syncError: text("sync_error"),
  status: text("status").notNull().default("active"), // active | gone
});

export const spreadsheetRows = pgTable(
  "spreadsheet_rows",
  {
    id: serial("id").primaryKey(),
    spreadsheetId: integer("spreadsheet_id").notNull().references(() => spreadsheets.id),
    tabName: text("tab_name").notNull(),
    rowNumber: integer("row_number").notNull(),
    name: text("name"),
    priceRaw: text("price_raw"),
    currency: text("currency"),
    imageUrl: text("image_url"),
    rawLink: text("raw_link"),
    productUrl: text("product_url"),
    platform: text("platform"),
    itemId: integer("item_id").references(() => items.id),
    requestedAt: timestamp("requested_at", { withTimezone: true }),
    promoteError: text("promote_error"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [unique("spreadsheet_rows_sheet_tab_row_unique").on(t.spreadsheetId, t.tabName, t.rowNumber)],
);

export const itemSpreadsheetMentions = pgTable(
  "item_spreadsheet_mentions",
  {
    itemId: integer("item_id").notNull().references(() => items.id),
    spreadsheetId: integer("spreadsheet_id").notNull().references(() => spreadsheets.id),
  },
  (t) => [primaryKey({ columns: [t.itemId, t.spreadsheetId] })],
);

// Vetted Weidian stores from the community mega-list; note is the curator's blurb.
export const stores = pgTable("stores", {
  id: serial("id").primaryKey(),
  userid: text("userid").notNull().unique(),
  name: text("name"),
  note: text("note"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});
