import Link from "next/link";
import { StoreControls } from "@/components/StoreControls";
import { getStores, type StoreSort } from "@/db/queries";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ q?: string; sort?: string }>;

export default async function StoresPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const q = params.q?.trim();
  const sort = (["rate", "items", "name"].includes(params.sort ?? "") ? params.sort : "rate") as StoreSort;
  const stores = await getStores({ q, sort });

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Vetted stores</h1>
        <p className="text-sm text-zinc-500">
          Curated Weidian stores from the community mega-list. Repeat-buyer rate: higher = more people order again.
        </p>
      </header>
      <StoreControls current={{ q: params.q, sort: params.sort }} />

      {stores.length === 0 ? (
        <p className="text-zinc-500 py-16 text-center">{q ? "No stores match." : "No stores yet."}</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {stores.map((s) => (
            <li key={s.userid}>
              <Link
                href={`/?shop=${s.userid}`}
                className="block h-full rounded-xl border border-zinc-200 bg-white p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <h2 className="font-semibold">{s.name ?? "Store"}</h2>
                  {s.rebuyRate != null && (
                    <span className="shrink-0 text-xs font-medium text-emerald-700">{s.rebuyRate}% repeat</span>
                  )}
                </div>
                {s.note && <p className="mt-1 text-sm italic text-zinc-600">&ldquo;{s.note}&rdquo;</p>}
                <p className="mt-2 text-xs text-zinc-400">{s.itemCount.toLocaleString()} items →</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
