export type AvatarBody = 'M' | 'F'

export type AvatarPreset = {
  url: string
  body: AvatarBody
}

const AVATAR_BASE = '/avatars'

export const FEMALE_AVATAR_PRESETS: AvatarPreset[] = [
  { url: `${AVATAR_BASE}/brunette.glb`, body: 'F' },
  // { url: `${AVATAR_BASE}/brunette-t.glb`, body: 'F' },
  { url: `${AVATAR_BASE}/mpfb.glb`, body: 'F' },
  // { url: `${AVATAR_BASE}/avatarsdk.glb`, body: 'F' },
  { url: `${AVATAR_BASE}/avaturn.glb`, body: 'F' },
  // { url: `${AVATAR_BASE}/vroid.glb`, body: 'F' }, // Loading error for vroid.glb: THREE.GLTFLoader: setMeshoptDecoder must be called before loading compressed files
]

export const MALE_AVATAR_PRESETS: AvatarPreset[] = [
  // { url: `${AVATAR_BASE}/brunette.glb`, body: 'M' },
  // { url: `${AVATAR_BASE}/brunette-t.glb`, body: 'M' },
  // { url: `${AVATAR_BASE}/mpfb.glb`, body: 'M' },
  { url: `${AVATAR_BASE}/avatarsdk.glb`, body: 'M' },
  // { url: `${AVATAR_BASE}/avaturn.glb`, body: 'M' },
  // { url: `${AVATAR_BASE}/vroid.glb`, body: 'M' },
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
