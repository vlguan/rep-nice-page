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
  "rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-700 hover:border-zinc-400";

export function FilterBar({ brands, categories, current }: Props) {
  const router = useRouter();
  const nav = (patch: Record<string, string | undefined>) => router.push(buildHref(current, patch));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <form action="" method="get" className="flex flex-1 min-w-56 gap-2">
        {current.category && <input type="hidden" name="category" value={current.category} />}
        {current.brand && <input type="hidden" name="brand" value={current.brand} />}
        {current.sort && <input type="hidden" name="sort" value={current.sort} />}
        <input
          type="search"
          name="q"
          defaultValue={current.q ?? ""}
          placeholder="Search items… (e.g. hellstar hoodie)"
          className="flex-1 rounded border border-zinc-300 px-3 py-1.5 text-sm"
        />
        <button type="submit" className="rounded bg-zinc-900 text-white px-3 py-1.5 text-sm">
          Search
        </button>
      </form>
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
      <select
        aria-label="Sort"
        className={selectClass}
        value={current.sort ?? "trending"}
        onChange={(e) => nav({ sort: e.target.value })}
      >
        <option value="trending">Trending</option>
        <option value="newest">Newest</option>
        <option value="price">Price</option>
      </select>
    </div>
  );
}
