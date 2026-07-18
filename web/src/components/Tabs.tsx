"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Top-of-page tab bar. Rendered once in the root layout so it persists across
// navigation and keeps a constant size regardless of each page's content width.
const TABS = [
  { href: "/", label: "All items" },
  { href: "/trending", label: "Trending" },
  { href: "/slept-on", label: "Slept on" },
  { href: "/stores", label: "Vetted stores" },
] as const;

export function Tabs() {
  const pathname = usePathname();
  return (
    // -mx-4 px-4 lets the underline span the full width inside the padded header
    <nav className="-mx-4 flex gap-1 overflow-x-auto border-b border-zinc-200 px-4" aria-label="Sections">
      {TABS.map((t) => {
        const isActive = t.href === "/" ? pathname === "/" : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={isActive ? "page" : undefined}
            className={`shrink-0 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? "border-zinc-900 text-zinc-900"
                : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
