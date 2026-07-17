import Link from "next/link";
import type { ItemCardData } from "@/db/queries";
import { cnyToUsd } from "@/lib/format";
import { ItemImage } from "./ItemImage";

export function ItemCard({ item }: { item: ItemCardData }) {
  const cover = item.imageUrls?.[0] ?? null;
  const price = item.priceCny ? Number(item.priceCny) : null;
  // Reddit items lead with post count; store-seeded items lead with sales.
  const meta =
    item.mentionCount > 0
      ? `${item.mentionCount} post${item.mentionCount === 1 ? "" : "s"}`
      : item.sold != null
        ? `${item.sold.toLocaleString()} sold`
        : null;
  return (
    <Link
      href={`/item/${item.id}`}
      className="group block touch-manipulation rounded-xl border border-zinc-200 bg-white overflow-hidden hover:shadow-md transition-shadow"
    >
      <div className="aspect-square overflow-hidden bg-zinc-100">
        <ItemImage
          src={cover}
          alt={item.titleEn ?? "item"}
          className="h-full w-full object-cover transition-transform [@media(hover:hover)]:group-hover:scale-105"
        />
      </div>
      <div className="p-3 space-y-1">
        {item.brand && (
          <span className="inline-block text-xs font-medium bg-zinc-100 rounded-full px-2 py-0.5">
            {item.brand}
          </span>
        )}
        <h3 className="text-sm font-medium line-clamp-2">{item.titleEn ?? "Untitled"}</h3>
        <div className="flex items-baseline justify-between text-sm">
          {price !== null ? (
            <span>
              ¥{price.toFixed(0)}{" "}
              <span className="text-zinc-500">≈ ${cnyToUsd(price).toFixed(0)}</span>
            </span>
          ) : (
            <span className="text-zinc-400">price unknown</span>
          )}
          {meta && <span className="text-xs text-zinc-500">{meta}</span>}
        </div>
      </div>
    </Link>
  );
}
