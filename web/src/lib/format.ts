export const CNY_TO_USD = 0.14; // rough fixed rate; update occasionally

export function cnyToUsd(cny: number): number {
  return cny * CNY_TO_USD;
}

const URL_RE =
  /https?:\/\/\S+|\S*(?:weidian\.com|taobao\.com|cnfans\.com|acbuy\.com|mulebuy\.com|allchinabuy\.com|superbuy\.com|kakobuy\.com)\S*/gi;
// lines that are just a label ("W2C:", "link", "cop") carry no review content
const CONNECTOR_RE = /^(?:w2c|link|links|rep|reps|cop|here|source|src|item|qc)[\s:.\-–—]*$/i;

/**
 * Turn a stored Reddit quote into display-ready review bullets: split into
 * lines, strip purchase URLs and leading list markers, and drop empty or
 * label-only lines. Returns [] when nothing quotable remains.
 */
export function reviewBullets(quote: string | null | undefined): string[] {
  if (!quote) return [];
  const seen = new Set<string>();
  const bullets: string[] = [];
  for (const raw of quote.split(/\r?\n/)) {
    const line = raw
      .replace(URL_RE, "")
      .replace(/^[\s•\-–—*·|>:]+/, "")
      .replace(/\s+/g, " ")
      .trim();
    const key = line.toLowerCase();
    if (line.length < 4 || CONNECTOR_RE.test(line) || seen.has(key)) continue;
    seen.add(key);
    bullets.push(line);
  }
  return bullets;
}
