"use client";

import { useRouter } from "next/navigation";
import { recordDismiss } from "@/lib/taste";

/** Small "not interested" control overlaid on a recommendation card. */
export function DismissButton({ itemId }: { itemId: number }) {
  const router = useRouter();
  return (
    <button
      type="button"
      aria-label="Not interested"
      title="Not interested"
      onClick={() => {
        recordDismiss(itemId);
        router.refresh();
      }}
      className="absolute right-1.5 top-1.5 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-zinc-200 bg-white/90 text-xs leading-none text-zinc-500 shadow-sm hover:bg-white hover:text-zinc-800"
    >
      ✕
    </button>
  );
}
