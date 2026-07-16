"use client";

import { useRouter } from "next/navigation";

type Props = {
  brands: string[];
  categories: string[];
  current: { category?: string; brand?: string; sort?: string; q?: string };
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

export function FilterBar({ brands, categories, current }: Props) {
  const router = useRouter();
  const nav = (patch: Record<string, string | undefined>) => router.push(buildHref(current, patch));

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex w-full sm:w-auto rounded-lg border border-zinc-300 overflow-hidden">
          {(["trending", "newest", "price"] as const).map((s) => {
            const active = (current.sort ?? "trending") === s;
            return (
              <button
                key={s}
                type="button"
                onClick={() => nav({ sort: s })}
                className={`flex-1 sm:flex-none px-3 py-1.5 text-sm capitalize ${
                  active ? "bg-zinc-900 text-white" : "bg-white text-zinc-700 hover:bg-zinc-100"
                }`}
              >
                {s}
              </button>
            );
          })}
        </div>
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
