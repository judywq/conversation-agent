export type LipSyncPayload = {
  words: string[]
  wtimes: number[]
  wdurations: number[]
}

export function isLipSyncPayload(value: unknown): value is LipSyncPayload {
  if (!value || typeof value !== 'object') return false
  const payload = value as LipSyncPayload
  return (
    Array.isArray(payload.words) &&
    Array.isArray(payload.wtimes) &&
    Array.isArray(payload.wdurations) &&
    payload.words.length > 0 &&
    payload.words.length === payload.wtimes.length &&
    payload.words.length === payload.wdurations.length
  )
}
