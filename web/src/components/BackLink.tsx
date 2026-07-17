"use client";

import { useRouter } from "next/navigation";
import { CATALOG_URL_KEY } from "./CatalogTracker";

/**
 * Returns to the last catalog view (home with the same search/filters/page),
 * skipping any items reached via "more like this". Falls back to the catalog
 * home when there's no remembered view (e.g. opened from a shared link).
 */
export function BackLink({ className }: { className?: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        const url = typeof window !== "undefined" ? sessionStorage.getItem(CATALOG_URL_KEY) : null;
        router.push(url || "/");
      }}
      className={className}
    >
      ← back to results
    </button>
  );
}
