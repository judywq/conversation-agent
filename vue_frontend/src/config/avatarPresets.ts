import type { Live2DPresetInput } from '@/composables/useLive2D'

export type AvatarBody = 'M' | 'F'

export type AvatarPreset = Live2DPresetInput

// Live2D official sample models (see public/live2d/README.md for setup + license).
// zoom/anchorY left at useLive2D defaults; per-model framing tune deferred (Task 6).
export const FEMALE_AVATAR_PRESETS: AvatarPreset[] = [
  { url: '/live2d/hiyori/Hiyori.model3.json' },
  { url: '/live2d/haru/Haru.model3.json' },
  { url: '/live2d/mao/Mao.model3.json' },
]

export const MALE_AVATAR_PRESETS: AvatarPreset[] = [{ url: '/live2d/natori/Natori.model3.json' }]

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
