import Link from "next/link";

// Shared header nav so /trending, /slept-on, /stores and home stay consistent.
const LINKS = [
  { href: "/trending", label: "Trending" },
  { href: "/slept-on", label: "Slept on" },
  { href: "/stores", label: "Vetted stores" },
] as const;

export function NavLinks({ active }: { active?: string }) {
  return (
    <>
      {LINKS.map((it) => (
        <Link
          key={it.href}
          href={it.href}
          className={`rounded-lg border px-3 py-1.5 text-sm ${
            active === it.href
              ? "border-zinc-900 bg-zinc-900 text-white"
              : "border-zinc-300 text-zinc-700 hover:bg-zinc-100"
          }`}
        >
          {it.label}
        </Link>
      ))}
    </>
  );
}
