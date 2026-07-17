import type { Metadata } from "next";
import Link from "next/link";
import { ItemCard } from "@/components/ItemCard";
import { NavLinks } from "@/components/NavLinks";
import { Pagination } from "@/components/Pagination";
import { getTrending, PAGE_SIZE } from "@/db/queries";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Trending",
  description: "What the rep community is hyping right now.",
};

type SearchParams = Promise<{ page?: string }>;

export default async function TrendingPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page) || 1);
  const { items, total } = await getTrending({ page });

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link href="/" className="text-sm text-zinc-500 hover:underline">← back to all items</Link>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <NavLinks active="/trending" />
        </div>
      </div>
      <header>
        <h1 className="text-2xl font-bold">🔥 Trending</h1>
        <p className="text-sm text-zinc-500">What the community is hyping right now.</p>
      </header>

      {items.length === 0 ? (
        <p className="text-zinc-500 py-16 text-center">
          Nothing trending yet — check back after the next scrape.
        </p>
      ) : (
        <>
          <p className="text-xs text-zinc-500">
            {total.toLocaleString()} item{total === 1 ? "" : "s"}
            {total > PAGE_SIZE && ` · page ${page} of ${Math.ceil(total / PAGE_SIZE)}`}
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {items.map((item) => (
              <ItemCard key={item.id} item={item} />
            ))}
          </div>
          <Pagination page={page} total={total} pageSize={PAGE_SIZE} current={{}} basePath="/trending" />
        </>
      )}
    </main>
  );
}
