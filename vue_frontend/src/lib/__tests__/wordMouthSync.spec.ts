import { describe, it, expect } from 'vitest'
import { mouthOpenFromWords } from '@/lib/wordMouthSync'

describe('mouthOpenFromWords', () => {
  const lipsync = {
    wtimes: [0, 300],
    wdurations: [200, 400],
  }

  it('returns 0 outside any word window', () => {
    expect(mouthOpenFromWords(-1, lipsync)).toBe(0)
    expect(mouthOpenFromWords(250, lipsync)).toBe(0)
    expect(mouthOpenFromWords(800, lipsync)).toBe(0)
  })

  it('opens mid-word and closes near word edges', () => {
    const mid = mouthOpenFromWords(100, lipsync) // middle of first 200ms word
    const nearStart = mouthOpenFromWords(5, lipsync)
    const nearEnd = mouthOpenFromWords(195, lipsync)
    expect(mid).toBeGreaterThan(0.7)
    expect(nearStart).toBeLessThan(mid)
    expect(nearEnd).toBeLessThan(mid)
  })

  it('returns 0 exactly at word end (end exclusive)', () => {
    expect(mouthOpenFromWords(200, lipsync)).toBe(0)
  })

  it('uses multiple flaps for long words', () => {
    const long = { wtimes: [0], wdurations: [480] } // ~3 flaps
    const a = mouthOpenFromWords(80, long)
    const trough = mouthOpenFromWords(160, long) // between flaps
    const b = mouthOpenFromWords(240, long)
    expect(a).toBeGreaterThan(0.5)
    expect(trough).toBeLessThan(0.2)
    expect(b).toBeGreaterThan(0.5)
  })
})
