export function superbuyUrl(weidianUrl: string): string {
  return `https://www.superbuy.com/en/page/buy/?url=${encodeURIComponent(weidianUrl)}`;
}
