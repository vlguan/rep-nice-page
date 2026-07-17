// Lightweight browsing-taste tracking via a cookie. Each item view appends
// [style, brand] to a capped recency list; the server reads it to recommend.

export const TASTE_COOKIE = "taste";
export const DISMISSED_COOKIE = "dismissed";
const MAX = 15;
const MAX_DISMISSED = 200;
const MAX_AGE = 60 * 60 * 24 * 30; // 30 days

type Pair = [string, string];

function decode(raw: string | undefined): Pair[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(decodeURIComponent(raw));
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

/** Server-side: turn the cookie into frequency-ranked styles + brands. */
export function parseTaste(raw: string | undefined): { styles: string[]; brands: string[] } {
  const styleFreq = new Map<string, number>();
  const brandFreq = new Map<string, number>();
  for (const p of decode(raw)) {
    const [s, b] = Array.isArray(p) ? p : ["", ""];
    if (s) styleFreq.set(s, (styleFreq.get(s) ?? 0) + 1);
    if (b) brandFreq.set(b, (brandFreq.get(b) ?? 0) + 1);
  }
  const byFreq = (m: Map<string, number>) =>
    [...m.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
  return { styles: byFreq(styleFreq).slice(0, 3), brands: byFreq(brandFreq).slice(0, 5) };
}

/** Client-side: record a viewed item's style + brand into the cookie. */
export function recordView(style: string | null, brand: string | null): void {
  if (typeof document === "undefined" || (!style && !brand)) return;
  const raw = document.cookie.match(/(?:^|;\s*)taste=([^;]*)/)?.[1];
  const head: Pair = [style ?? "", brand ?? ""];
  const pairs: Pair[] = [head, ...decode(raw)].slice(0, MAX);
  document.cookie = `${TASTE_COOKIE}=${encodeURIComponent(JSON.stringify(pairs))}; path=/; max-age=${MAX_AGE}; samesite=lax`;
}

/** Server-side: item ids the user marked "not interested". */
export function parseDismissed(raw: string | undefined): number[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(decodeURIComponent(raw));
    return Array.isArray(v) ? v.filter((n) => typeof n === "number") : [];
  } catch {
    return [];
  }
}

/** Client-side: mark an item "not interested" so it stops being recommended. */
export function recordDismiss(id: number): void {
  if (typeof document === "undefined") return;
  const raw = document.cookie.match(/(?:^|;\s*)dismissed=([^;]*)/)?.[1];
  const ids = [id, ...parseDismissed(raw).filter((x) => x !== id)].slice(0, MAX_DISMISSED);
  document.cookie = `${DISMISSED_COOKIE}=${encodeURIComponent(JSON.stringify(ids))}; path=/; max-age=${MAX_AGE}; samesite=lax`;
}
