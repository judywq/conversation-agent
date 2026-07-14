import type { LipSyncPayload } from '@/types/lipsync'

/** One jaw flap roughly every this many ms for long words. */
const FLAP_MS = 160
const PEAK_OPEN = 0.9

/**
 * Mouth open amount (0..1) at playback time `tMs`, driven by word timings.
 * Short words get a single open–close; longer words get multiple flaps.
 */
export function mouthOpenFromWords(
  tMs: number,
  lipsync: Pick<LipSyncPayload, 'wtimes' | 'wdurations'>,
): number {
  const { wtimes, wdurations } = lipsync
  for (let i = 0; i < wtimes.length; i++) {
    const start = wtimes[i]!
    const dur = Math.max(wdurations[i] ?? 1, 1)
    if (tMs < start || tMs >= start + dur) continue
    const local = (tMs - start) / dur
    const flaps = Math.max(1, Math.round(dur / FLAP_MS))
    return PEAK_OPEN * Math.abs(Math.sin(local * Math.PI * flaps))
  }
  return 0
}
