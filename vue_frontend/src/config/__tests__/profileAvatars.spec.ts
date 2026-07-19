import { describe, expect, it } from 'vitest'
import { profileAvatarById, isProfileAvatarId } from '../profileAvatars'

describe('profileAvatars', () => {
  it('resolves known ids', () => {
    expect(profileAvatarById('fox')?.url).toBe('/avatars/fox.png')
    expect(profileAvatarById('rabbit')?.label).toBe('Rabbit')
    expect(profileAvatarById('cat')?.id).toBe('cat')
  })

  it('rejects unknown ids', () => {
    expect(profileAvatarById('dragon')).toBeUndefined()
    expect(profileAvatarById('')).toBeUndefined()
    expect(profileAvatarById(null)).toBeUndefined()
    expect(isProfileAvatarId('fox')).toBe(true)
    expect(isProfileAvatarId('dragon')).toBe(false)
  })
})
