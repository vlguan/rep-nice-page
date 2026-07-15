const WEIDIAN_ID = /[?&]itemID=(\d+)/i;
const TAOBAO_ID = /[?&]id=(\d+)/i;

export function superbuyUrl(
  productUrl: string,
  platform: string = "weidian",
  partnerCode: string | undefined = process.env.SUPERBUY_PARTNER_CODE,
): string {
  const idRe = platform === "taobao" ? TAOBAO_ID : WEIDIAN_ID;
  const platformCode = platform === "taobao" ? "TB" : "WD";
  const match = productUrl.match(idRe);
  if (!match) {
    return `https://www.superbuy.com/en/page/buy/?url=${encodeURIComponent(productUrl)}`;
  }
  // partnercode attributes new-user registrations from this handoff to our
  // affiliate account; trackPayload mirrors Superbuy's own share links.
  const partner = partnerCode ? `&partnercode=${partnerCode}&trackPayload=pc_share` : "";
  return `https://www.superbuy.com/en/page/buy/?platform=${platformCode}&id=${match[1]}${partner}`;
}
