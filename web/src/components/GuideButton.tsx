"use client";

import { useState } from "react";
import { SUPERBUY_GUIDE } from "@/content/superbuy-guide";

export function GuideButton({ label = "How to buy" }: { label?: string }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100"
      >
        {label}
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-zinc-200 p-4">
              <h2 className="font-bold">{SUPERBUY_GUIDE.title}</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close guide"
                className="rounded px-2 py-1 text-zinc-500 hover:bg-zinc-100"
              >
                ✕
              </button>
            </div>
            <div className="overflow-y-auto p-4 text-sm text-zinc-700 whitespace-pre-line">
              {SUPERBUY_GUIDE.text}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
