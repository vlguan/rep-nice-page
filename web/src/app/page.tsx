import { FilterBar } from "@/components/FilterBar";
import { ItemCard } from "@/components/ItemCard";
import { getFilterOptions, getItems, type SortKey } from "@/db/queries";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ category?: string; brand?: string; sort?: string }>;

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const sort = (["trending", "newest", "price"].includes(params.sort ?? "") ? params.sort : "trending") as SortKey;
  const [itemList, filterOptions] = await Promise.all([
    getItems({ category: params.category, brand: params.brand, sort }),
    getFilterOptions(),
  ]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Digital Canal Street</h1>
        <p className="text-sm text-zinc-500">
          trending rep fashion, begin chinamaxxing
        </p>
      </header>
      <FilterBar
        brands={filterOptions.brands}
        categories={filterOptions.categories}
        current={{ category: params.category, brand: params.brand, sort: params.sort }}
      />
      {itemList.length === 0 ? (
        <p className="text-zinc-500 py-16 text-center">No items yet — the scraper hasn&apos;t run.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {itemList.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </main>
  );
}
