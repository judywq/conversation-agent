/** Ordered list — cycling uses this order. Append new slugs when adding backgrounds. */
export const PARTNER_CARD_BG_SLUGS = [
  'sakura-classroom',
  'sakura-park',
  'sakura-cafe',
  'sakura-library',
  'rooftop-sunset',
  'rainy-courtyard',
  'sakura-campus',
  'sakura-courtyard',
] as const

export function partnerCardBgUrl(index: number): string {
  const slug = PARTNER_CARD_BG_SLUGS[index % PARTNER_CARD_BG_SLUGS.length]
  return `/partner-card-bgs/${slug}.webp`
}
