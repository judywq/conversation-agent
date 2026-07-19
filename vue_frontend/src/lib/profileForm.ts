import type { User } from '@/types/auth'
import type { CefrSample } from '@/services/conversationService'
import { z } from 'zod'

export const OCEAN_LEVELS = ['low', 'medium', 'high'] as const
export const OCEAN_UNSET = '__unset__'

export type OceanTraitKey =
  | 'openness'
  | 'conscientiousness'
  | 'extraversion'
  | 'agreeableness'
  | 'neuroticism'

export type OceanTraitConfig = {
  key: OceanTraitKey
  label: string
  description: string
}

export const oceanLevelSchema = z.enum(OCEAN_LEVELS, {
  required_error: 'Select a level',
  invalid_type_error: 'Select a level',
})

export const oceanFormSchema = z.object({
  openness: oceanLevelSchema,
  conscientiousness: oceanLevelSchema,
  extraversion: oceanLevelSchema,
  agreeableness: oceanLevelSchema,
  neuroticism: oceanLevelSchema,
})

export type OceanFormValues = z.infer<typeof oceanFormSchema>

export const OCEAN_TRAITS: OceanTraitConfig[] = [
  {
    key: 'openness',
    label: 'Openness',
    description:
      'Openness describes how willing you are to explore new ideas, perspectives, and experiences. Higher openness often means more curiosity and creativity, while lower openness often means preferring familiarity and structure.',
  },
  {
    key: 'conscientiousness',
    label: 'Conscientiousness',
    description:
      'Conscientiousness describes how organized, careful, and responsible you are. Higher conscientiousness often means planning carefully and noticing details, while lower conscientiousness often means being more spontaneous and less structured.',
  },
  {
    key: 'extraversion',
    label: 'Extraversion',
    description:
      'Extraversion describes how energetic, expressive, and socially active you are. Higher extraversion often means enjoying lively interaction, while lower extraversion often means being quieter and more reflective.',
  },
  {
    key: 'agreeableness',
    label: 'Agreeableness',
    description:
      'Agreeableness describes how cooperative, kind, and supportive you are with other people. Higher agreeableness often means being patient and encouraging, while lower agreeableness often means being more direct or skeptical.',
  },
  {
    key: 'neuroticism',
    label: 'Neuroticism',
    description:
      'Neuroticism describes how strongly you experience stress, worry, or emotional ups and downs. Higher neuroticism often means greater sensitivity to pressure, while lower neuroticism often means feeling calmer and steadier.',
  },
]

export function oceanFormValuesFromModel(
  ocean: Record<OceanTraitKey, string>,
): Partial<OceanFormValues> {
  const values: Partial<OceanFormValues> = {}
  for (const { key } of OCEAN_TRAITS) {
    const v = ocean[key]
    if (v && v !== OCEAN_UNSET && OCEAN_LEVELS.includes(v as (typeof OCEAN_LEVELS)[number])) {
      values[key] = v as (typeof OCEAN_LEVELS)[number]
    }
  }
  return values
}

export type ProfileStep = 1 | 2 | 3

export type ProfileFormState = {
  preferredName: string
  major: string
  avatarId: string
  ocean: Record<OceanTraitKey, string>
  selectedCefrLevel: string | null
  cefrSamples: CefrSample[]
}

export function emptyOceanModel(user?: User | null): Record<OceanTraitKey, string> {
  return {
    openness: user?.ocean?.openness ?? OCEAN_UNSET,
    conscientiousness: user?.ocean?.conscientiousness ?? OCEAN_UNSET,
    extraversion: user?.ocean?.extraversion ?? OCEAN_UNSET,
    agreeableness: user?.ocean?.agreeableness ?? OCEAN_UNSET,
    neuroticism: user?.ocean?.neuroticism ?? OCEAN_UNSET,
  }
}

export function buildOceanPayload(ocean: Record<OceanTraitKey, string>): Record<string, string> {
  const oceanPayload: Record<string, string> = {}
  for (const { key } of OCEAN_TRAITS) {
    const v = ocean[key]
    if (v && v !== OCEAN_UNSET) oceanPayload[key] = v
  }
  return oceanPayload
}

export function isAboutComplete(preferredName: string, major: string): boolean {
  return Boolean(preferredName.trim() && major.trim())
}

export function isOceanComplete(ocean: Record<OceanTraitKey, string>): boolean {
  return OCEAN_TRAITS.every(({ key }) => {
    const v = ocean[key]
    return Boolean(v && v !== OCEAN_UNSET)
  })
}

export function isCefrComplete(cefrLevel: string | null | undefined): boolean {
  return Boolean((cefrLevel ?? '').trim())
}

export function firstIncompleteStep(user?: User | null): ProfileStep {
  const preferredName = user?.preferred_name ?? ''
  const major = user?.major ?? ''
  if (!isAboutComplete(preferredName, major)) return 1

  const ocean = emptyOceanModel(user)
  if (!isOceanComplete(ocean)) return 2

  return 3
}

export function validateStep(step: ProfileStep, state: ProfileFormState): string | null {
  if (step === 1) {
    if (!state.preferredName.trim()) return 'Enter how we should address you.'
    if (!state.major.trim()) return 'Enter your study major.'
    return null
  }
  if (step === 2) {
    for (const { key, label } of OCEAN_TRAITS) {
      const v = state.ocean[key]
      if (!v || v === OCEAN_UNSET) return `Select a level for ${label}.`
    }
    return null
  }
  if (!state.selectedCefrLevel) return 'Choose a CEFR listening level.'
  return null
}

export function aboutPayload(state: Pick<ProfileFormState, 'preferredName' | 'major' | 'avatarId'>) {
  return {
    preferred_name: state.preferredName,
    major: state.major,
    avatar_id: state.avatarId,
  }
}

export function oceanPayload(state: Pick<ProfileFormState, 'ocean'>) {
  return {
    ocean: buildOceanPayload(state.ocean),
  }
}

export function cefrPayload(state: Pick<ProfileFormState, 'selectedCefrLevel' | 'cefrSamples'>, topic: string) {
  return {
    cefr_level: state.selectedCefrLevel,
    cefr_sample_topic: topic,
    cefr_sample_choices: state.cefrSamples,
  }
}
