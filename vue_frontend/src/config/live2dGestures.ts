import type { Live2DCapabilities } from '@/composables/useLive2D'

export const LIVE2D_GESTURES_LIST = ['idle', 'speak', 'think'] as const

export type Live2DGesture = (typeof LIVE2D_GESTURES_LIST)[number]

export type Live2DGestureMap = Record<Live2DGesture, string[]>

/**
 * Logical gesture → Cubism motion display names (capabilities name =
 * manifest Name or basename of .motion3.json).
 * Keyed by model folder under /live2d/ (e.g. haru).
 *
 * Guessing heuristic (every motion from model3.json assigned once):
 * - idle: Cubism Idle group
 * - speak: Tap / TapBody (and talk-like sounds); Flick when it is a greeting/wave
 * - think: remaining Flick/Shake/specials, or Info-style TapBody clips
 */
export const LIVE2D_GESTURES: Record<string, Live2DGestureMap> = {
  chitose: {
    idle: ['chitose_idle'],
    speak: ['chitose_handwave'],
    think: ['chitose_kime01', 'chitose_kime02'],
  },
  epsilon: {
    idle: ['Epsilon_idle_01'],
    speak: [
      'Epsilon_m_02',
      'Epsilon_m_07',
      'Epsilon_m_03',
      'Epsilon_m_sp_02',
      'Epsilon_m_sp_03',
      'Epsilon_m_sp_05',
    ],
    think: [
      'Epsilon_m_01',
      'Epsilon_m_05',
      'Epsilon_m_04',
      'Epsilon_m_sp_01',
      'Epsilon_m_06',
      'Epsilon_m_08',
      'Epsilon_m_sp_04',
      'Epsilon_shake_01',
    ],
  },
  haru: {
    idle: ['haru_g_idle', 'haru_g_m15'],
    // TapBody: talk/normal → speak; Info clips → think
    speak: ['haru_g_m26', 'haru_g_m20'],
    think: ['haru_g_m06', 'haru_g_m09'],
  },
  hibiki: {
    idle: ['hibiki_01', 'hibiki_02', 'hibiki_05'],
    speak: ['hibiki_02'],
    think: ['hibiki_03'],
  },
  hiyori: {
    idle: [
      'Hiyori_m01',
      'Hiyori_m02',
      'Hiyori_m03',
      'Hiyori_m06',
      'Hiyori_m07',
      'Hiyori_m08',
      'Hiyori_m09',
      'Hiyori_m10',
    ],
    speak: [
      'Hiyori_m04',
      'Hiyori_m05',
    ],
    think: [],
  },
  // No Idle group; language intro clips treated as speak.
  kei: {
    idle: [],
    speak: ['01_kei_en', '01_kei_jp', '01_kei_ko', '01_kei_zh'],
    think: [],
  },
  mao: {
    idle: ['mtn_01', 'sample_01'],
    speak: ['mtn_02', 'mtn_03', 'mtn_04'],
    think: ['special_01', 'special_02', 'special_03'],
  },
  natori: {
    idle: ['mtn_00', 'mtn_01', 'mtn_02'],
    speak: ['mtn_03', 'mtn_04', 'mtn_05'],
    think: ['mtn_06', 'mtn_07'],
  },
  ren: {
    idle: ['mtn_01'],
    speak: ['mtn_02'],
    think: ['mtn_03'],
  },
  shizuku: {
    idle: ['04'],
    speak: ['02'],
    think: ['01', '03'],
  },
}

/** Folder segment from `/live2d/<key>/...model3.json`. */
export function live2dModelKeyFromUrl(url: string): string | null {
  const parts = url.split('/').filter(Boolean)
  const i = parts.findIndex((p) => p === 'live2d')
  if (i < 0 || i + 1 >= parts.length) return null
  return parts[i + 1] ?? null
}

export function gesturesForUrl(url: string): Live2DGestureMap | undefined {
  const key = live2dModelKeyFromUrl(url)
  return key ? LIVE2D_GESTURES[key] : undefined
}

export type ResolvedGestureMotion = {
  group: string
  index: number
  name: string
}

/** Map logical gesture + index → Cubism (group, index) via capabilities names. */
export function resolveGestureMotion(
  capabilities: Live2DCapabilities,
  gestureMap: Live2DGestureMap,
  gesture: Live2DGesture,
  index: number,
): ResolvedGestureMotion | null {
  const names = gestureMap[gesture] ?? []
  if (!Number.isInteger(index) || index < 0 || index >= names.length) return null
  const name = names[index]
  if (!name) return null

  for (const { group, motions } of capabilities.motionGroups) {
    const entry = motions.find((m) => m.name === name)
    if (entry) return { group, index: entry.index, name }
  }
  return null
}

/** Pick a random motion from a logical gesture group (empty → null). */
export function resolveRandomGestureMotion(
  capabilities: Live2DCapabilities,
  gestureMap: Live2DGestureMap,
  gesture: Live2DGesture,
): ResolvedGestureMotion | null {
  const names = gestureMap[gesture] ?? []
  if (names.length === 0) return null
  const index = Math.floor(Math.random() * names.length)
  return resolveGestureMotion(capabilities, gestureMap, gesture, index)
}
