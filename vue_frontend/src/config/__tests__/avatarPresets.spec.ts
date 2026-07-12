import { describe, it, expect } from 'vitest'
import {
  avatarPresetForAgent,
  FEMALE_AVATAR_PRESETS,
  MALE_AVATAR_PRESETS,
  normalizeAvatarBody,
} from '../avatarPresets'

describe('avatarPresets', () => {
  it('all presets point at Live2D model manifests', () => {
    for (const p of [...FEMALE_AVATAR_PRESETS, ...MALE_AVATAR_PRESETS]) {
      expect(p.url).toMatch(/^\/live2d\/.+\.model3\.json$/)
    }
  })

  it('maps gender strings to preset pools', () => {
    expect(normalizeAvatarBody('male')).toBe('M')
    expect(normalizeAvatarBody('M')).toBe('M')
    expect(normalizeAvatarBody('female')).toBe('F')
    expect(normalizeAvatarBody(undefined)).toBe('F')
  })

  it('cycles presets by index within the gender pool', () => {
    expect(avatarPresetForAgent('female', 0)).toBe(FEMALE_AVATAR_PRESETS[0])
    expect(avatarPresetForAgent('female', FEMALE_AVATAR_PRESETS.length)).toBe(
      FEMALE_AVATAR_PRESETS[0],
    )
    expect(avatarPresetForAgent('male', 1)).toBe(
      MALE_AVATAR_PRESETS[1 % MALE_AVATAR_PRESETS.length],
    )
  })
})
