import Link from "next/link";
import { notFound } from "next/navigation";
import { ItemImage } from "@/components/ItemImage";
import { getItemDetail } from "@/db/queries";
import { cnyToUsd } from "@/lib/format";
import { superbuyUrl } from "@/lib/superbuy";

export const dynamic = "force-dynamic";

export default async function ItemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isInteger(numericId)) notFound();
  const item = await getItemDetail(numericId);
  if (!item) notFound();

  const price = item.priceCny ? Number(item.priceCny) : null;
  const summary = item.mentions.find((m) => m.aiSummary)?.aiSummary;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">← back to all items</Link>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <div className="aspect-square rounded-xl overflow-hidden bg-zinc-100">
            <ItemImage src={item.imageUrls?.[0] ?? null} alt={item.titleEn ?? "item"} className="h-full w-full object-cover" />
          </div>
          {(item.imageUrls?.length ?? 0) > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-1 snap-x">
              {item.imageUrls!.map((url) => (
                <div key={url} className="w-24 h-24 shrink-0 snap-start rounded-lg overflow-hidden bg-zinc-100">
                  <ItemImage src={url} alt="" className="h-full w-full object-cover" />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {item.brand && <span className="inline-block text-xs font-medium bg-zinc-100 rounded-full px-2 py-0.5">{item.brand}</span>}
          <h1 className="text-xl font-bold">{item.titleEn ?? "Untitled"}</h1>
          {price !== null && (
            <p className="text-lg">
              ¥{price.toFixed(0)} <span className="text-zinc-500 text-sm">≈ ${cnyToUsd(price).toFixed(0)} USD</span>
            </p>
          )}
          {item.sellerName && <p className="text-sm text-zinc-500">Seller: {item.sellerName}</p>}

          <a
            href={superbuyUrl(item.productUrl, item.platform)}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-xl bg-zinc-900 text-white text-center py-3 font-medium hover:bg-zinc-700"
          >
            Buy via Superbuy →
          </a>
          <a
            href={item.productUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-xl border border-zinc-300 text-center py-2 text-sm hover:bg-zinc-50"
          >
            View original on {item.platform === "taobao" ? "Taobao" : "Weidian"}
          </a>

          {item.descriptionEn && <p className="text-sm text-zinc-700 whitespace-pre-line">{item.descriptionEn}</p>}

          {summary && (
            <details className="rounded-xl bg-amber-50 border border-amber-200">
              <summary className="cursor-pointer select-none p-3 text-xs font-semibold uppercase text-amber-700">
                Community verdict (AI summary)
              </summary>
              <p className="px-3 pb-3 text-sm text-amber-900">{summary}</p>
            </details>
          )}

          <div>
            <h2 className="text-xs font-semibold uppercase text-zinc-500 mb-2">
              Seen in {item.mentions.length} Reddit post{item.mentions.length === 1 ? "" : "s"}
            </h2>
            <ul className="space-y-1">
              {item.mentions.map((m) => (
                <li key={m.permalink}>
                  <a href={m.permalink ?? "#"} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline">
                    {m.title ?? m.permalink} <span className="text-zinc-400">({m.score ?? 0} pts)</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </main>
  );
}
