import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";
import { Banner } from "@/components/Banner";
import { CatalogTracker } from "@/components/CatalogTracker";
import { FilterBar } from "@/components/FilterBar";
import { GuideButton } from "@/components/GuideButton";
import { ItemCard } from "@/components/ItemCard";
import { Pagination } from "@/components/Pagination";
import { RecommendationRow } from "@/components/RecommendationRow";
import { StagingCard } from "@/components/StagingCard";
import { flagRowsForPromotion, getFilterOptions, getItems, getRecommendations, PAGE_SIZE, searchItems, searchStagingRows, type SortKey } from "@/db/queries";
import { DISMISSED_COOKIE, parseDismissed, parseTaste, TASTE_COOKIE } from "@/lib/taste";

export const dynamic = "force-dynamic";

// Home share-preview image (drop web/public/banner.png in). Absolute URL is
// resolved via metadataBase in the root layout.
export const metadata: Metadata = {
  openGraph: {
    title: "Digital Canal St",
    description: "Curated replica fashion catalog with one-click Superbuy links",
    images: ["/banner.png"],
  },
  twitter: { card: "summary_large_image", images: ["/banner.png"] },
};

type SearchParams = Promise<{ category?: string; brand?: string; style?: string; sort?: string; q?: string; shop?: string; page?: string }>;

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const sort = (["trending", "newest", "price"].includes(params.sort ?? "") ? params.sort : "trending") as SortKey;
  const q = params.q?.trim();
  const page = Math.max(1, Number(params.page) || 1);
  const [result, filterOptions, stagingRows] = await Promise.all([
    q ? searchItems(q, { category: params.category, brand: params.brand, page }) : getItems({ category: params.category, brand: params.brand, style: params.style, sort, shop: params.shop, page }),
    getFilterOptions(),
    q ? searchStagingRows(q) : Promise.resolve([]),
  ]);
  const { items: itemList, total } = result;
  if (q) void flagRowsForPromotion(q).catch(() => {});

  // "For you" — only on the bare catalog view (no search/filters, first page).
  const bareView = !q && !params.category && !params.brand && !params.style && !params.shop && page === 1;
  const cookieStore = await cookies();
  const taste = parseTaste(cookieStore.get(TASTE_COOKIE)?.value);
  const dismissed = parseDismissed(cookieStore.get(DISMISSED_COOKIE)?.value);
  const recs = bareView && (taste.styles.length || taste.brands.length)
    ? await getRecommendations({ styles: taste.styles, brands: taste.brands, excludeIds: dismissed })
    : [];

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <Suspense fallback={null}>
        <CatalogTracker />
      </Suspense>
      <Banner />
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Digital Canal St</h1>
          <p className="text-sm text-zinc-500">
            trending rep fashion, begin chinamaxxing
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            href="/stores"
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100"
          >
            Vetted stores
          </Link>
          <GuideButton />
        </div>
      </header>
      <FilterBar
        brands={filterOptions.brands}
        categories={filterOptions.categories}
        styles={filterOptions.styles}
        current={{ category: params.category, brand: params.brand, style: params.style, sort: params.sort, q: params.q }}
      />
      {recs.length > 0 && (
        <RecommendationRow
          title="For you"
          subtitle={`Because you've been browsing ${(taste.styles.slice(0, 2).join(" & ") || taste.brands[0])}`}
          items={recs}
        />
      )}
      {itemList.length === 0 ? (
        <p className="text-zinc-500 py-16 text-center">
          {total === 0 ? "No items match." : "No items on this page."}
        </p>
      ) : (
        <>
          <p className="text-xs text-zinc-500">
            {total.toLocaleString()} item{total === 1 ? "" : "s"}
            {total > PAGE_SIZE && ` · page ${page} of ${Math.ceil(total / PAGE_SIZE)}`}
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {itemList.map((item) => (
              <ItemCard key={item.id} item={item} />
            ))}
          </div>
          <Pagination
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            current={{ category: params.category, brand: params.brand, style: params.style, sort: params.sort, q: params.q, shop: params.shop }}
          />
        </>
      )}
      {stagingRows.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">From community spreadsheets</h2>
          <p className="text-xs text-zinc-500">These match your search but aren&apos;t fully cataloged yet — they&apos;re being fetched now and appear above on your next search.</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {stagingRows.map((row) => (
              <StagingCard key={row.id} row={row} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
