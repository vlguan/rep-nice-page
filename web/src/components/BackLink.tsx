"use client";

import { useRouter } from "next/navigation";

/**
 * Goes back to the previous page (preserving the search/filters/page the user
 * came from). Falls back to the catalog when there's no in-app history — e.g.
 * the item was opened from a shared link or a new tab.
 */
export function BackLink({ className }: { className?: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        if (window.history.length > 1) router.back();
        else router.push("/");
      }}
      className={className}
    >
      ← back
    </button>
  );
}
