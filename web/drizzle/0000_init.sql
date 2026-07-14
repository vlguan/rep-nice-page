CREATE TABLE "item_mentions" (
	"item_id" integer NOT NULL,
	"reddit_post_id" integer NOT NULL,
	CONSTRAINT "item_mentions_item_id_reddit_post_id_pk" PRIMARY KEY("item_id","reddit_post_id")
);
--> statement-breakpoint
CREATE TABLE "items" (
	"id" serial PRIMARY KEY NOT NULL,
	"weidian_url" text NOT NULL,
	"weidian_item_id" text,
	"title_zh" text,
	"title_en" text,
	"description_en" text,
	"brand" text,
	"category" text,
	"price_cny" numeric,
	"seller_name" text,
	"image_urls" jsonb,
	"status" text DEFAULT 'active' NOT NULL,
	"last_validated_at" timestamp with time zone,
	"dead_since" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now(),
	"updated_at" timestamp with time zone DEFAULT now(),
	CONSTRAINT "items_weidian_url_unique" UNIQUE("weidian_url")
);
--> statement-breakpoint
CREATE TABLE "reddit_posts" (
	"id" serial PRIMARY KEY NOT NULL,
	"reddit_post_id" text NOT NULL,
	"permalink" text,
	"title" text,
	"subreddit" text,
	"score" integer,
	"num_comments" integer,
	"posted_at" timestamp with time zone,
	"scraped_at" timestamp with time zone,
	"sentiment" text,
	"ai_summary" text,
	CONSTRAINT "reddit_posts_reddit_post_id_unique" UNIQUE("reddit_post_id")
);
--> statement-breakpoint
CREATE TABLE "scrape_runs" (
	"id" serial PRIMARY KEY NOT NULL,
	"started_at" timestamp with time zone,
	"finished_at" timestamp with time zone,
	"posts_seen" integer,
	"items_added" integer,
	"items_deactivated" integer,
	"error" text
);
--> statement-breakpoint
ALTER TABLE "item_mentions" ADD CONSTRAINT "item_mentions_item_id_items_id_fk" FOREIGN KEY ("item_id") REFERENCES "public"."items"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "item_mentions" ADD CONSTRAINT "item_mentions_reddit_post_id_reddit_posts_id_fk" FOREIGN KEY ("reddit_post_id") REFERENCES "public"."reddit_posts"("id") ON DELETE no action ON UPDATE no action;