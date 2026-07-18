import type { Live2DPresetInput } from '@/composables/useLive2D'

export type AvatarBody = 'M' | 'F'

export type AvatarPreset = Live2DPresetInput

/** Multiplier applied to every model's zoom (pre-game, in-game, debug). */
export const AVATAR_GLOBAL_ZOOM = 0.8

/** Fallback per-model zoom when a preset omits `zoom`. */
export const AVATAR_DEFAULT_ZOOM = 2.4

/** Effective zoom: (modelZoom ?? default) × global × optional user size slider. */
export function resolveAvatarZoom(modelZoom?: number, userScale = 1): number {
  return (modelZoom ?? AVATAR_DEFAULT_ZOOM) * AVATAR_GLOBAL_ZOOM * userScale
}

// Live2D official sample models (see public/live2d/README.md for setup + license).
// Per-model zoom (and optional anchorY) tuned via /debug/avatars, then pasted here.
export const FEMALE_AVATAR_PRESETS: AvatarPreset[] = [
  { url: '/live2d/hiyori/Hiyori.model3.json', zoom: 2.4 },
  { url: '/live2d/haru/Haru.model3.json' },
  { url: '/live2d/mao/Mao.model3.json', zoom: 4.8 },
  { url: '/live2d/epsilon/Epsilon_free.model3.json', zoom: 1.6 },
  { url: '/live2d/hibiki/hibiki.model3.json' },
  { url: '/live2d/shizuku/shizuku.model3.json', zoom: 1.3 },
  { url: '/live2d/kei/kei_basic_free.model3.json', zoom: 0.9 },
]

export const MALE_AVATAR_PRESETS: AvatarPreset[] = [
  { url: '/live2d/natori/Natori.model3.json', zoom: 3.8 },
  { url: '/live2d/chitose/chitose.model3.json' },
]

export function normalizeAvatarBody(gender?: string | null): AvatarBody {
  const value = (gender || '').trim().toLowerCase()
  if (value === 'm' || value === 'male') return 'M'
  return 'F'
}

export function avatarPresetForAgent(
  gender: string | undefined | null,
  index: number,
): AvatarPreset {
  const body = normalizeAvatarBody(gender)
  const presets = body === 'M' ? MALE_AVATAR_PRESETS : FEMALE_AVATAR_PRESETS
  return presets[index % presets.length]!
}

export function avatarPresetByUrl(url: string): AvatarPreset | undefined {
  return [...FEMALE_AVATAR_PRESETS, ...MALE_AVATAR_PRESETS].find((p) => p.url === url)
}
