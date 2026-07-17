import { ItemCard } from "./ItemCard";
import type { ItemCardData } from "@/db/queries";

export function RecommendationRow({
  title,
  subtitle,
  items,
}: {
  title: string;
  subtitle?: string;
  items: ItemCardData[];
}) {
  if (items.length === 0) return null;
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        {subtitle && <p className="text-xs text-zinc-500">{subtitle}</p>}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {items.map((i) => (
          <ItemCard key={i.id} item={i} />
        ))}
      </div>
    </section>
  );
}
