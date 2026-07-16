import Link from "next/link";
import { notFound } from "next/navigation";
import { GuideButton } from "@/components/GuideButton";
import { ItemGallery } from "@/components/ItemGallery";
import { getItemDetail } from "@/db/queries";
import { cnyToUsd, reviewQuote } from "@/lib/format";
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

  // One continuous verbatim review per Reddit comment, deduped, best score first.
  const reviewMap = new Map<string, { text: string; score: number; permalink: string | null }>();
  for (const m of item.mentions) {
    const text = reviewQuote(m.quote);
    if (!text) continue;
    const key = text.toLowerCase();
    const prev = reviewMap.get(key);
    if (!prev || (m.score ?? 0) > prev.score) {
      reviewMap.set(key, { text, score: m.score ?? 0, permalink: m.permalink });
    }
  }
  const reviews = [...reviewMap.values()].sort((a, b) => b.score - a.score);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">← back to all items</Link>

      <div className="grid md:grid-cols-2 gap-6">
        <ItemGallery images={item.imageUrls ?? []} alt={item.titleEn ?? "item"} />

        <div className="space-y-4">
          {item.brand && <span className="inline-block text-xs font-medium bg-zinc-100 rounded-full px-2 py-0.5">{item.brand}</span>}
          <h1 className="text-xl font-bold">{item.titleEn ?? "Untitled"}</h1>
          {price !== null && (
            <p className="text-lg">
              ¥{price.toFixed(0)} <span className="text-zinc-500 text-sm">≈ ${cnyToUsd(price).toFixed(0)} USD</span>
            </p>
          )}
          {item.sellerName && <p className="text-sm text-zinc-500">Seller: {item.sellerName}</p>}
          {item.sellerRebuyRate !== null && (
            <p className="text-sm">
              <span className="font-medium text-emerald-700">{item.sellerRebuyRate}% repeat customers</span>{" "}
              <span className="text-zinc-400">
                — share of this vendor&apos;s buyers who come back and order again
              </span>
            </p>
          )}

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
          <GuideButton label="New to agents? How buying works" />

          {item.descriptionEn && <p className="text-sm text-zinc-700 whitespace-pre-line">{item.descriptionEn}</p>}

          {reviews.length > 0 && (
            <div>
              <h2 className="text-xs font-semibold uppercase text-zinc-500 mb-2">Reviews (from Reddit)</h2>
              <ul className="space-y-3">
                {reviews.map((r) => (
                  <li key={r.text} className="text-sm text-zinc-800">
                    <span className="italic">&ldquo;{r.text}&rdquo;</span>{" "}
                    {r.permalink ? (
                      <a
                        href={r.permalink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-zinc-400 hover:text-blue-600 hover:underline whitespace-nowrap"
                      >
                        — {r.score} pts
                      </a>
                    ) : (
                      <span className="text-zinc-400 whitespace-nowrap">— {r.score} pts</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
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

          {summary && (
            <details className="text-xs text-zinc-400">
              <summary className="cursor-pointer select-none hover:text-zinc-600">AI summary of the discussion</summary>
              <p className="mt-1 text-zinc-500">{summary}</p>
            </details>
          )}
        </div>
      </div>
    </main>
  );
}
