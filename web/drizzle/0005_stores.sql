CREATE TABLE "stores" (
	"id" serial PRIMARY KEY NOT NULL,
	"userid" text NOT NULL UNIQUE,
	"name" text,
	"note" text,
	"created_at" timestamp with time zone DEFAULT now()
);
--> statement-breakpoint
ALTER TABLE "items" ADD COLUMN "shop_userid" text;
--> statement-breakpoint
CREATE INDEX "items_shop_userid_idx" ON "items" ("shop_userid");
