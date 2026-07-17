"use client";

import { useState } from "react";

/**
 * Home hero banner. Renders /banner.png (drop your ~1200x630 artwork there);
 * hides itself gracefully until the file exists.
 */
export function Banner() {
  const [ok, setOk] = useState(true);
  if (!ok) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/banner.png"
      alt="Digital Canal St"
      onError={() => setOk(false)}
      className="w-full rounded-xl border border-zinc-200"
    />
  );
}
