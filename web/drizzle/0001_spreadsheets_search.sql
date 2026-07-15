CREATE EXTENSION IF NOT EXISTS pg_trgm;
--> statement-breakpoint
ALTER TABLE "items" RENAME COLUMN "weidian_url" TO "product_url";
--> statement-breakpoint
ALTER TABLE "items" RENAME COLUMN "weidian_item_id" TO "platform_item_id";
--> statement-breakpoint
ALTER TABLE "items" ADD COLUMN "platform" text NOT NULL DEFAULT 'weidian';
--> statement-breakpoint
CREATE TABLE "spreadsheets" (
	"id" serial PRIMARY KEY NOT NULL,
	"sheet_key" text NOT NULL UNIQUE,
	"url" text NOT NULL,
	"title" text,
	"discovered_post_id" integer REFERENCES "reddit_posts"("id"),
	"discovered_at" timestamp with time zone DEFAULT now(),
	"last_synced_at" timestamp with time zone,
	"sync_error" text,
	"status" text NOT NULL DEFAULT 'active'
);
--> statement-breakpoint
CREATE TABLE "spreadsheet_rows" (
	"id" serial PRIMARY KEY NOT NULL,
	"spreadsheet_id" integer NOT NULL REFERENCES "spreadsheets"("id"),
	"tab_name" text NOT NULL,
	"row_number" integer NOT NULL,
	"name" text,
	"price_raw" text,
	"currency" text,
	"image_url" text,
	"raw_link" text,
	"product_url" text,
	"platform" text,
	"item_id" integer REFERENCES "items"("id"),
	"requested_at" timestamp with time zone,
	"promote_error" text,
	"created_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "spreadsheet_rows_sheet_tab_row_unique" UNIQUE("spreadsheet_id","tab_name","row_number")
);
--> statement-breakpoint
CREATE TABLE "item_spreadsheet_mentions" (
	"item_id" integer NOT NULL REFERENCES "items"("id"),
	"spreadsheet_id" integer NOT NULL REFERENCES "spreadsheets"("id"),
	CONSTRAINT "item_spreadsheet_mentions_pk" PRIMARY KEY("item_id","spreadsheet_id")
);
--> statement-breakpoint
CREATE INDEX "items_title_en_trgm" ON "items" USING gin ("title_en" gin_trgm_ops);
--> statement-breakpoint
CREATE INDEX "items_brand_trgm" ON "items" USING gin ("brand" gin_trgm_ops);
--> statement-breakpoint
CREATE INDEX "spreadsheet_rows_name_trgm" ON "spreadsheet_rows" USING gin ("name" gin_trgm_ops);
