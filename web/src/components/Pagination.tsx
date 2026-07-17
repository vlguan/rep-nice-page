import Link from "next/link";

type Current = { category?: string; brand?: string; style?: string; sort?: string; q?: string; shop?: string };

function hrefFor(current: Current, page: number, basePath: string) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(current)) if (v) params.set(k, v);
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

const base = "min-w-9 rounded-lg border px-3 py-1.5 text-sm text-center";
const link = "border-zinc-300 text-zinc-700 hover:bg-zinc-100";
const activeCls = "border-zinc-900 bg-zinc-900 text-white";
const disabled = "border-zinc-200 text-zinc-300 pointer-events-none";

export function Pagination({
  page,
  total,
  pageSize,
  current,
  basePath = "/",
}: {
  page: number;
  total: number;
  pageSize: number;
  current: Current;
  basePath?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;
  const cur = Math.min(Math.max(1, page), totalPages);

  const win = 2;
  const start = Math.max(1, cur - win);
  const end = Math.min(totalPages, cur + win);
  const nums = Array.from({ length: end - start + 1 }, (_, i) => start + i);

  return (
    <nav className="flex flex-wrap items-center justify-center gap-1.5 pt-2" aria-label="Pagination">
      <Link
        href={hrefFor(current, cur - 1, basePath)}
        aria-disabled={cur === 1}
        className={`${base} ${cur === 1 ? disabled : link}`}
      >
        ← Prev
      </Link>
      {start > 1 && (
        <>
          <Link href={hrefFor(current, 1, basePath)} className={`${base} ${link}`}>1</Link>
          {start > 2 && <span className="px-1 text-zinc-400">…</span>}
        </>
      )}
      {nums.map((n) => (
        <Link
          key={n}
          href={hrefFor(current, n, basePath)}
          aria-current={n === cur ? "page" : undefined}
          className={`${base} ${n === cur ? activeCls : link}`}
        >
          {n}
        </Link>
      ))}
      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span className="px-1 text-zinc-400">…</span>}
          <Link href={hrefFor(current, totalPages, basePath)} className={`${base} ${link}`}>{totalPages}</Link>
        </>
      )}
      <Link
        href={hrefFor(current, cur + 1, basePath)}
        aria-disabled={cur === totalPages}
        className={`${base} ${cur === totalPages ? disabled : link}`}
      >
        Next →
      </Link>
    </nav>
  );
}
