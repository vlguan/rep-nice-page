export const CNY_TO_USD = 0.14; // rough fixed rate; update occasionally

export function cnyToUsd(cny: number): number {
  return cny * CNY_TO_USD;
}
