export const CNY_TO_USD = 0.14; // rough fixed rate; update occasionally

export function cnyToUsd(cny: number): number {
  return cny * CNY_TO_USD;
}

const URL_RE =
  /https?:\/\/\S+|\S*(?:weidian\.com|taobao\.com|cnfans\.com|acbuy\.com|mulebuy\.com|allchinabuy\.com|superbuy\.com|kakobuy\.com)\S*/gi;
// lines that are just a label ("W2C:", "link", "cop") carry no review content
const CONNECTOR_RE = /^(?:w2c|link|links|rep|reps|cop|here|source|src|item|qc)[\s:.\-–—]*$/i;

// haul enumeration labels ("7. Stüssy Thermal (Size M)") head a comment but
// aren't review prose — the item title already shows above the reviews.
const LABEL_RE = /^\d+[.)]\s/;

/**
 * Turn a stored Reddit quote into ONE continuous review string: strip purchase
 * URLs, leading list markers, label-only and enumeration lines, then join the
 * remaining lines into a single quote. Returns null when nothing quotable
 * remains. A single comment stays a single review — it is never split.
 */
export function reviewQuote(quote: string | null | undefined): string | null {
  if (!quote) return null;
  const parts: string[] = [];
  for (const raw of quote.split(/\r?\n/)) {
    const line = raw
      .replace(URL_RE, "")
      .replace(/^[\s•\-–—*·|>:]+/, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!line || CONNECTOR_RE.test(line) || LABEL_RE.test(line)) continue;
    parts.push(line);
  }
  const text = parts.join(" ").trim();
  return text.length >= 4 ? text : null;
}
