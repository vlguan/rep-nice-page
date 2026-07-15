import { superbuyUrl } from "@/lib/superbuy";
import type { StagingCardData } from "@/db/queries";
import { ItemImage } from "@/components/ItemImage";
import { cnyToUsd } from "@/lib/format";

export function StagingCard({ row }: { row: StagingCardData }) {
  const price =
    row.priceRaw && row.currency === "CNY"
      ? `¥${row.priceRaw} · ~$${cnyToUsd(Number(row.priceRaw.replace(/[^\d.]/g, "")) || 0).toFixed(0)}`
      : row.priceRaw && row.currency === "USD"
        ? `$${row.priceRaw}`
        : null;
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 p-3 space-y-2">
      <ItemImage src={row.imageUrl ?? null} alt={row.name ?? "spreadsheet item"} />
      <h3 className="text-sm font-medium line-clamp-2">{row.name ?? "Untitled"}</h3>
      {price && <p className="text-sm text-zinc-600">{price}</p>}
      <p className="text-xs text-zinc-400">from {row.sheetTitle ?? "a community spreadsheet"} · full details loading…</p>
      <a
        href={superbuyUrl(row.productUrl, row.platform)}
        target="_blank"
        rel="noreferrer"
        className="block text-center rounded bg-zinc-900 text-white text-sm py-1.5"
      >
        Buy via Superbuy
      </a>
    </div>
  );
}
