import Link from "next/link";

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

function Chip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className={`rounded-full px-3 py-1 text-sm border ${
        active ? "bg-zinc-900 text-white border-zinc-900" : "border-zinc-300 hover:bg-zinc-100"
      }`}
    >
      {children}
    </Link>
  );
}

export function FilterBar({ brands, categories, current }: Props) {
  return (
    <div className="space-y-2">
      <form action="" method="get" className="flex gap-2">
        {current.category && <input type="hidden" name="category" value={current.category} />}
        {current.brand && <input type="hidden" name="brand" value={current.brand} />}
        {current.sort && <input type="hidden" name="sort" value={current.sort} />}
        <input
          type="search"
          name="q"
          defaultValue={current.q ?? ""}
          placeholder="Search items… (e.g. hellstar hoodie)"
          className="rounded border border-zinc-300 px-3 py-1.5 text-sm w-56"
        />
        <button type="submit" className="rounded bg-zinc-900 text-white px-3 py-1.5 text-sm">
          Search
        </button>
      </form>
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase text-zinc-500 w-16">Sort</span>
        {(["trending", "newest", "price"] as const).map((s) => (
          <Chip key={s} href={buildHref(current, { sort: s })} active={(current.sort ?? "trending") === s}>
            {s}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase text-zinc-500 w-16">Category</span>
        <Chip href={buildHref(current, { category: undefined })} active={!current.category}>all</Chip>
        {categories.map((c) => (
          <Chip key={c} href={buildHref(current, { category: c })} active={current.category === c}>
            {c}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase text-zinc-500 w-16">Brand</span>
        <Chip href={buildHref(current, { brand: undefined })} active={!current.brand}>all</Chip>
        {brands.map((b) => (
          <Chip key={b} href={buildHref(current, { brand: b })} active={current.brand === b}>
            {b}
          </Chip>
        ))}
      </div>
    </div>
  );
}
