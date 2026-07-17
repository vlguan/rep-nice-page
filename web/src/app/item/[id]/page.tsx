import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { BackLink } from "@/components/BackLink";
import { GuideButton } from "@/components/GuideButton";
import { ItemGallery } from "@/components/ItemGallery";
import { RecommendationRow } from "@/components/RecommendationRow";
import { TrackView } from "@/components/TrackView";
import { getItemDetail, getRecommendations } from "@/db/queries";
import { DISMISSED_COOKIE, parseDismissed } from "@/lib/taste";
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

  const dismissed = parseDismissed((await cookies()).get(DISMISSED_COOKIE)?.value);
  const more = await getRecommendations({
    styles: item.style ? [item.style] : [],
    brands: item.brand ? [item.brand] : [],
    excludeIds: [item.id, ...dismissed],
  });

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 space-y-8">
      <TrackView style={item.style} brand={item.brand} />
      <BackLink className="text-sm text-zinc-500 hover:underline" />

      <div className="grid md:grid-cols-2 gap-6 md:items-start">
        <ItemGallery images={item.imageUrls ?? []} alt={item.titleEn ?? "item"} />

        <div className="min-w-0 space-y-4 md:sticky md:top-8">
          {item.brand && <span className="inline-block text-xs font-medium bg-zinc-100 rounded-full px-2 py-0.5">{item.brand}</span>}
          <h1 className="text-xl font-bold">{item.titleEn ?? "Untitled"}</h1>
          {item.descriptionEn && <p className="text-sm text-zinc-700 whitespace-pre-line">{item.descriptionEn}</p>}
          {price !== null && (
            <p className="text-lg">
              ¥{price.toFixed(0)} <span className="text-zinc-500 text-sm">≈ ${cnyToUsd(price).toFixed(0)} USD</span>
            </p>
          )}
          {item.sold != null && <p className="text-sm text-zinc-500">{item.sold.toLocaleString()} sold</p>}
          {item.sellerName && <p className="text-sm text-zinc-500">Seller: {item.sellerName}</p>}
          {item.sellerRebuyRate !== null && !item.store?.note && (
            <p className="text-sm">
              <span className="font-medium text-emerald-700">{item.sellerRebuyRate}% repeat customers</span>{" "}
              <span className="text-zinc-400">
                — share of this vendor&apos;s buyers who come back and order again
              </span>
            </p>
          )}
          {item.store?.note && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
              <p className="text-sm text-emerald-900">
                <span className="font-semibold">{item.store.name ?? "Vetted store"}</span>
                {item.sellerRebuyRate !== null && (
                  <span className="text-emerald-700"> · {item.sellerRebuyRate}% repeat buyers</span>
                )}
              </p>
              <p className="mt-1 text-sm italic text-emerald-800">&ldquo;{item.store.note}&rdquo;</p>
              <p className="mt-1 text-xs text-emerald-600">
                from the <Link href="/stores" className="underline">vetted store list</Link>
              </p>
            </div>
          )}

          <a
            href={superbuyUrl(item.productUrl, item.platform)}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full rounded-xl bg-zinc-900 text-white text-center py-3 font-medium hover:bg-zinc-700"
          >
            Buy via Superbuy →
          </a>
          <GuideButton label="New to agents? How buying works" />
        </div>
      </div>

      {reviews.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold uppercase text-zinc-500 mb-3">Reviews (from Reddit)</h2>
          <ul className="space-y-3 max-w-2xl">
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
        </section>
      )}

      {summary && (
        <details className="text-xs text-zinc-400">
          <summary className="cursor-pointer select-none hover:text-zinc-600">AI summary of the discussion</summary>
          <p className="mt-1 text-zinc-500 max-w-2xl">{summary}</p>
        </details>
      )}

      <RecommendationRow title="More like this" items={more} />
    </main>
  );
}
