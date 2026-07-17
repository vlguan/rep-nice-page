"use client";

import { useRouter } from "next/navigation";

type Props = {
  brands: string[];
  categories: string[];
  styles: string[];
  current: { category?: string; brand?: string; style?: string; sort?: string; q?: string };
};

function buildHref(current: Props["current"], patch: Record<string, string | undefined>) {
  const params = new URLSearchParams();
  const merged = { ...current, ...patch };
  for (const [k, v] of Object.entries(merged)) if (v) params.set(k, v);
  const qs = params.toString();
  return qs ? `/?${qs}` : "/";
}

const selectClass =
  "min-w-0 flex-1 truncate rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-700 hover:border-zinc-400 sm:flex-none sm:w-36";

export function FilterBar({ brands, categories, styles, current }: Props) {
  const router = useRouter();
  const nav = (patch: Record<string, string | undefined>) => router.push(buildHref(current, patch));

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex w-full sm:w-auto rounded-lg border border-zinc-300 overflow-hidden">
          {([
            { key: "trending", label: "Trending" },
            { key: "newest", label: "Newest" },
            { key: "price", label: "Price" },
            { key: "value", label: "Best value" },
          ] as const).map((s) => {
            const active = (current.sort ?? "trending") === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => nav({ sort: s.key })}
                className={`flex-1 sm:flex-none whitespace-nowrap px-3 py-1.5 text-sm ${
                  active ? "bg-zinc-900 text-white" : "bg-white text-zinc-700 hover:bg-zinc-100"
                }`}
              >
                {s.label}
              </button>
            );
          })}
        </div>
        <select
        aria-label="Style"
        className={selectClass}
        value={current.style ?? ""}
        onChange={(e) => nav({ style: e.target.value || undefined })}
      >
        <option value="">All styles</option>
        {styles.map((s) => (
          <option key={s} value={s} className="capitalize">
            {s}
          </option>
        ))}
      </select>
        <select
        aria-label="Category"
        className={selectClass}
        value={current.category ?? ""}
        onChange={(e) => nav({ category: e.target.value || undefined })}
      >
        <option value="">All categories</option>
        {categories.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <select
        aria-label="Brand"
        className={selectClass}
        value={current.brand ?? ""}
        onChange={(e) => nav({ brand: e.target.value || undefined })}
      >
        <option value="">All brands</option>
        {brands.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>
      </div>
      <form action="" method="get" className="flex items-center gap-1.5 w-full sm:w-auto">
        {current.category && <input type="hidden" name="category" value={current.category} />}
        {current.brand && <input type="hidden" name="brand" value={current.brand} />}
        {current.sort && <input type="hidden" name="sort" value={current.sort} />}
        <input
          type="search"
          name="q"
          defaultValue={current.q ?? ""}
          placeholder="Search items…"
          onChange={(e) => {
            // Emptying the box (delete or the native × clear) resets to the
            // full list, keeping any category/brand/sort filters.
            if (e.target.value.trim() === "" && current.q) nav({ q: undefined });
          }}
          className="min-w-0 flex-1 sm:flex-none sm:w-56 rounded border border-zinc-300 px-3 py-1.5 text-sm"
        />
        <button
          type="submit"
          className="rounded bg-zinc-900 text-white px-2.5 py-1.5 text-xs hover:bg-zinc-700"
        >
          Go
        </button>
      </form>
    </div>
  );
}
