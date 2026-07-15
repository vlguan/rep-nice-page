const ITEM_ID = /[?&]itemID=(\d+)/i;

export function superbuyUrl(
  weidianUrl: string,
  partnerCode: string | undefined = process.env.SUPERBUY_PARTNER_CODE,
): string {
  const match = weidianUrl.match(ITEM_ID);
  if (!match) {
    return `https://www.superbuy.com/en/page/buy/?url=${encodeURIComponent(weidianUrl)}`;
  }
  // partnercode attributes new-user registrations from this handoff to our
  // affiliate account; trackPayload mirrors Superbuy's own share links.
  const partner = partnerCode ? `&partnercode=${partnerCode}&trackPayload=pc_share` : "";
  return `https://www.superbuy.com/en/page/buy/?platform=WD&id=${match[1]}${partner}`;
}
