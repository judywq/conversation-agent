export type AvatarBody = 'M' | 'F'

export type AvatarPreset = {
  url: string
  body: AvatarBody
}

const TALKING_HEAD_AVATARS =
  'https://raw.githubusercontent.com/met4citizen/TalkingHead/main/avatars'

export const FEMALE_AVATAR_PRESETS: AvatarPreset[] = [
  { url: `${TALKING_HEAD_AVATARS}/brunette.glb`, body: 'F' },
  { url: `${TALKING_HEAD_AVATARS}/mpfb.glb`, body: 'F' },
  { url: `${TALKING_HEAD_AVATARS}/brunette-t.glb`, body: 'F' },
  { url: `${TALKING_HEAD_AVATARS}/avaturn.glb`, body: 'F' },
  { url: `${TALKING_HEAD_AVATARS}/vroid.glb`, body: 'F' },
]

export const MALE_AVATAR_PRESETS: AvatarPreset[] = [
  { url: `${TALKING_HEAD_AVATARS}/avatarsdk.glb`, body: 'M' },
  { url: `${TALKING_HEAD_AVATARS}/vroid.glb`, body: 'M' },
  { url: `${TALKING_HEAD_AVATARS}/brunette.glb`, body: 'M' },
  { url: `${TALKING_HEAD_AVATARS}/mpfb.glb`, body: 'M' },
  { url: `${TALKING_HEAD_AVATARS}/avaturn.glb`, body: 'M' },
]

export function normalizeAvatarBody(gender?: string | null): AvatarBody {
  const value = (gender || '').trim().toLowerCase()
  if (value === 'm' || value === 'male') return 'M'
  return 'F'
}

export function avatarPresetForAgent(gender: string | undefined | null, index: number): AvatarPreset {
  const body = normalizeAvatarBody(gender)
  const presets = body === 'M' ? MALE_AVATAR_PRESETS : FEMALE_AVATAR_PRESETS
  return presets[index % presets.length]!
}
