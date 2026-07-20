import { describe, expect, it } from 'vitest'
import type { Live2DCapabilities } from '@/composables/useLive2D'
import {
  LIVE2D_GESTURES,
  gesturesForUrl,
  live2dModelKeyFromUrl,
  resolveGestureMotion,
} from '@/config/live2dGestures'

const caps: Live2DCapabilities = {
  idleGroup: 'Idle',
  expressions: [],
  motionGroups: [
    {
      group: 'Idle',
      motions: [
        { index: 0, name: 'haru_g_idle' },
        { index: 1, name: 'haru_g_m15' },
      ],
    },
    {
      group: 'TapBody',
      motions: [
        { index: 0, name: 'haru_g_m26' },
        { index: 1, name: 'haru_g_m06' },
      ],
    },
  ],
}

describe('live2dModelKeyFromUrl', () => {
  it('extracts folder after /live2d/', () => {
    expect(live2dModelKeyFromUrl('/live2d/haru/Haru.model3.json')).toBe('haru')
    expect(live2dModelKeyFromUrl('https://x.test/live2d/mao/Mao.model3.json')).toBe('mao')
  })

  it('returns null when path has no live2d segment', () => {
    expect(live2dModelKeyFromUrl('/models/haru/Haru.model3.json')).toBeNull()
  })
})

describe('gesturesForUrl', () => {
  it('returns the map for known models', () => {
    expect(gesturesForUrl('/live2d/haru/Haru.model3.json')?.idle).toEqual([
      'haru_g_idle',
      'haru_g_m15',
    ])
    expect(LIVE2D_GESTURES.haru.speak).toEqual(['haru_g_m26', 'haru_g_m20'])
  })
})

describe('resolveGestureMotion', () => {
  const map = LIVE2D_GESTURES.haru!

  it('resolves idle index to Cubism group+index', () => {
    expect(resolveGestureMotion(caps, map, 'idle', 1)).toEqual({
      group: 'Idle',
      index: 1,
      name: 'haru_g_m15',
    })
  })

  it('resolves speak names into TapBody', () => {
    expect(resolveGestureMotion(caps, map, 'speak', 0)).toEqual({
      group: 'TapBody',
      index: 0,
      name: 'haru_g_m26',
    })
  })

  it('returns null for out-of-range gesture entries', () => {
    expect(resolveGestureMotion(caps, map, 'idle', 9)).toBeNull()
    expect(resolveGestureMotion(caps, map, 'speak', 9)).toBeNull()
  })

  it('returns null when the motion name is missing from capabilities', () => {
    const orphan = { ...map, speak: ['missing_motion'] }
    expect(resolveGestureMotion(caps, orphan, 'speak', 0)).toBeNull()
  })
})
