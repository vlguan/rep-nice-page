export const TAGLINE_PREFIX = "trending rep fashion";

// A random one shows after the prefix on each (dynamic) page render.
const QUOTES = [
  "begin chinamaxxing",
  "you've heard of quiet luxury, but what about chinese luxury",
  "sometimes you just wanna show your boss you're spending his money correctly",
  "there's actually a sixth tier in the hierarchy of needs, and it's drip",
  "imagine pulling up to the function in full LV — wait, nvm, don't imagine that",
  "where east meets west",
  "don't pay $120 for that tee, just buy the $20 rep",
];

export function randomQuote(): string {
  return QUOTES[Math.floor(Math.random() * QUOTES.length)];
}
