"use client";

import { useEffect } from "react";
import { recordView } from "@/lib/taste";

/** Records the viewed item's style + brand into the taste cookie (client-only). */
export function TrackView({ style, brand }: { style: string | null; brand: string | null }) {
  useEffect(() => {
    recordView(style, brand);
  }, [style, brand]);
  return null;
}
