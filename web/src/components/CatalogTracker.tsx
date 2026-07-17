"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect } from "react";

export const CATALOG_URL_KEY = "catalogUrl";

/** Remembers the current catalog URL (path + query) so the item-page back
 *  button can return to the exact search/filters — not a previously-viewed
 *  item reached via "more like this". */
export function CatalogTracker() {
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    const qs = search.toString();
    sessionStorage.setItem(CATALOG_URL_KEY, pathname + (qs ? `?${qs}` : ""));
  }, [pathname, search]);
  return null;
}
