export const PROFILE_AVATARS = [
  // People
  { id: 'boy1', label: 'Boy 1', url: '/avatars/boy1.png' },
  { id: 'boy2', label: 'Boy 2', url: '/avatars/boy2.png' },
  { id: 'boy3', label: 'Boy 3', url: '/avatars/boy3.png' },
  { id: 'boy4', label: 'Boy 4', url: '/avatars/boy4.png' },
  { id: 'boy5', label: 'Boy 5', url: '/avatars/boy5.png' },
  { id: 'girl1', label: 'Girl 1', url: '/avatars/girl1.png' },
  { id: 'girl2', label: 'Girl 2', url: '/avatars/girl2.png' },
  { id: 'girl3', label: 'Girl 3', url: '/avatars/girl3.png' },
  { id: 'girl4', label: 'Girl 4', url: '/avatars/girl4.png' },
  { id: 'girl5', label: 'Girl 5', url: '/avatars/girl5.png' },
  // Animals
  { id: 'panda', label: 'Panda', url: '/avatars/panda.png' },
  { id: 'bear', label: 'Bear', url: '/avatars/bear.png' },
  { id: 'puppy', label: 'Puppy', url: '/avatars/puppy.png' },
  { id: 'penguin', label: 'Penguin', url: '/avatars/penguin.png' },
  { id: 'cat', label: 'Cat', url: '/avatars/cat.png' },
  { id: 'hamster', label: 'Hamster', url: '/avatars/hamster.png' },
  { id: 'deer', label: 'Deer', url: '/avatars/deer.png' },
  { id: 'chick', label: 'Chick', url: '/avatars/chick.png' },
  { id: 'koala', label: 'Koala', url: '/avatars/koala.png' },
  { id: 'frog', label: 'Frog', url: '/avatars/frog.png' },
] as const

export type ProfileAvatarId = (typeof PROFILE_AVATARS)[number]['id']

const ALLOWED_IDS = new Set<string>(PROFILE_AVATARS.map((a) => a.id))

export function isProfileAvatarId(id: string | null | undefined): id is ProfileAvatarId {
  return Boolean(id && ALLOWED_IDS.has(id))
}

export function profileAvatarById(id: string | null | undefined) {
  if (!isProfileAvatarId(id)) return undefined
  return PROFILE_AVATARS.find((a) => a.id === id)
}
