import { describe, expect, it } from 'vitest'
import { isLipSyncPayload } from '@/types/lipsync'

describe('isLipSyncPayload', () => {
  it('accepts valid lip-sync payloads', () => {
    expect(
      isLipSyncPayload({
        words: ['Hello', 'world'],
        wtimes: [0, 500],
        wdurations: [500, 700],
      }),
    ).toBe(true)
  })

  it('rejects mismatched arrays', () => {
    expect(
      isLipSyncPayload({
        words: ['Hello'],
        wtimes: [0, 500],
        wdurations: [500],
      }),
    ).toBe(false)
  })
})
