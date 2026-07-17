"use client";

import { useRouter } from "next/navigation";

type Current = { q?: string; sort?: string };

export function StoreControls({ current }: { current: Current }) {
  const router = useRouter();
  const nav = (patch: Record<string, string | undefined>) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries({ ...current, ...patch })) if (v) params.set(k, v);
    const qs = params.toString();
    router.push(qs ? `/stores?${qs}` : "/stores");
  };

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <select
        aria-label="Sort stores"
        className="min-w-0 flex-1 rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-700 hover:border-zinc-400 sm:flex-none sm:w-48"
        value={current.sort ?? "rate"}
        onChange={(e) => nav({ sort: e.target.value === "rate" ? undefined : e.target.value })}
      >
        <option value="rate">Highest repeat rate</option>
        <option value="items">Most items</option>
        <option value="name">Name (A–Z)</option>
      </select>
      <form action="/stores" method="get" className="flex items-center gap-1.5 w-full sm:w-auto">
        {current.sort && <input type="hidden" name="sort" value={current.sort} />}
        <input
          type="search"
          name="q"
          defaultValue={current.q ?? ""}
          placeholder="Search stores… (e.g. TNF, budget, shoes)"
          onChange={(e) => {
            if (e.target.value.trim() === "" && current.q) nav({ q: undefined });
          }}
          className="min-w-0 flex-1 sm:flex-none sm:w-64 rounded border border-zinc-300 px-3 py-1.5 text-sm"
        />
        <button type="submit" className="rounded bg-zinc-900 text-white px-2.5 py-1.5 text-xs hover:bg-zinc-700">
          Go
        </button>
      </form>
    </div>
  );
}
