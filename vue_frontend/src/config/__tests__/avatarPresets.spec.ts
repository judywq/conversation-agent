import { describe, it, expect } from 'vitest'
import {
  AVATAR_DEFAULT_ZOOM,
  AVATAR_GLOBAL_OFFSET_X,
  AVATAR_GLOBAL_OFFSET_Y,
  AVATAR_GLOBAL_ZOOM,
  avatarPresetByUrl,
  avatarPresetForAgent,
  FEMALE_AVATAR_PRESETS,
  MALE_AVATAR_PRESETS,
  normalizeAvatarBody,
  resolveAvatarOffset,
  resolveAvatarZoom,
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

  it('looks up presets by url', () => {
    expect(avatarPresetByUrl(FEMALE_AVATAR_PRESETS[0]!.url)).toBe(FEMALE_AVATAR_PRESETS[0])
    expect(avatarPresetByUrl(MALE_AVATAR_PRESETS[0]!.url)).toBe(MALE_AVATAR_PRESETS[0])
    expect(avatarPresetByUrl('/live2d/missing/Missing.model3.json')).toBeUndefined()
  })

  it('resolves zoom with global multiplier and optional user scale', () => {
    expect(resolveAvatarZoom(undefined)).toBe(AVATAR_DEFAULT_ZOOM * AVATAR_GLOBAL_ZOOM)
    expect(resolveAvatarZoom(2)).toBe(2 * AVATAR_GLOBAL_ZOOM)
    expect(resolveAvatarZoom(2, 1.5)).toBe(2 * AVATAR_GLOBAL_ZOOM * 1.5)
  })

  it('resolves offset by adding global to per-model', () => {
    expect(resolveAvatarOffset()).toEqual({
      offsetX: AVATAR_GLOBAL_OFFSET_X,
      offsetY: AVATAR_GLOBAL_OFFSET_Y,
    })
    expect(resolveAvatarOffset(10, -20)).toEqual({
      offsetX: 10 + AVATAR_GLOBAL_OFFSET_X,
      offsetY: -20 + AVATAR_GLOBAL_OFFSET_Y,
    })
  })
})
