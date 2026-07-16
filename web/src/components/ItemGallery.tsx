"use client";

import { useState } from "react";
import { ItemImage } from "./ItemImage";

export function ItemGallery({ images, alt }: { images: string[]; alt: string }) {
  const [active, setActive] = useState(0);
  const cover = images[active] ?? null;

  return (
    <div className="space-y-2">
      <div className="aspect-square rounded-xl overflow-hidden bg-zinc-100">
        <ItemImage src={cover} alt={alt} className="h-full w-full object-cover" />
      </div>
      {images.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1 snap-x">
          {images.map((url, i) => (
            <button
              key={url}
              type="button"
              onClick={() => setActive(i)}
              aria-label={`View image ${i + 1}`}
              aria-current={i === active}
              className={`w-24 h-24 shrink-0 snap-start rounded-lg overflow-hidden bg-zinc-100 transition ${
                i === active ? "ring-2 ring-zinc-900" : "ring-1 ring-transparent hover:ring-zinc-300"
              }`}
            >
              <ItemImage src={url} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
