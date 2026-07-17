import { FilterBar } from "@/components/FilterBar";
import { GuideButton } from "@/components/GuideButton";
import { ItemCard } from "@/components/ItemCard";
import { Pagination } from "@/components/Pagination";
import { StagingCard } from "@/components/StagingCard";
import { flagRowsForPromotion, getFilterOptions, getItems, PAGE_SIZE, searchItems, searchStagingRows, type SortKey } from "@/db/queries";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ category?: string; brand?: string; sort?: string; q?: string; page?: string }>;

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const sort = (["trending", "newest", "price"].includes(params.sort ?? "") ? params.sort : "trending") as SortKey;
  const q = params.q?.trim();
  const page = Math.max(1, Number(params.page) || 1);
  const [result, filterOptions, stagingRows] = await Promise.all([
    q ? searchItems(q, { category: params.category, brand: params.brand, page }) : getItems({ category: params.category, brand: params.brand, sort, page }),
    getFilterOptions(),
    q ? searchStagingRows(q) : Promise.resolve([]),
  ]);
  const { items: itemList, total } = result;
  if (q) void flagRowsForPromotion(q).catch(() => {});

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Digital Canal St</h1>
          <p className="text-sm text-zinc-500">
            trending rep fashion, begin chinamaxxing
          </p>
        </div>
        <GuideButton />
      </header>
      <FilterBar
        brands={filterOptions.brands}
        categories={filterOptions.categories}
        current={{ category: params.category, brand: params.brand, sort: params.sort, q: params.q }}
      />
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
            current={{ category: params.category, brand: params.brand, sort: params.sort, q: params.q }}
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
