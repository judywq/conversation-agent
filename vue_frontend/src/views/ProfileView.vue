<template>
  <div class="container mx-auto py-8 px-4">
    <Card class="mx-auto w-full rounded-2xl border-border/80 shadow-sm sm:max-w-3xl">
      <CardHeader class="space-y-3">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div class="space-y-1">
            <CardTitle class="text-2xl font-bold">My Profile</CardTitle>
            <CardDescription>
              Set up your language-learning profile before starting conversations.
            </CardDescription>
          </div>
          <div
            class="inline-flex w-fit items-center rounded-full border px-3 py-1 text-xs font-medium"
            :class="
              authStore.user?.profile_completed
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                : 'border-amber-200 bg-amber-50 text-amber-800'
            "
          >
            {{ authStore.user?.profile_completed ? 'Profile complete' : 'Profile incomplete' }}
          </div>
        </div>
      </CardHeader>
      <CardContent class="space-y-6">
        <section class="space-y-4 rounded-2xl border border-border/80 bg-muted/30 p-4 sm:p-5">
          <div class="space-y-1">
            <h2 class="text-base font-semibold">About you</h2>
            <p class="text-sm text-muted-foreground">
              Your name, study background, and personality help your discussion partners get to know you.
            </p>
          </div>

          <div class="space-y-4">
            <div class="space-y-2">
              <div class="text-sm font-medium">How should we address you?</div>
              <Input
                v-model="preferredName"
                placeholder="E.g., Alex"
                class="w-full"
              />
              <div class="text-xs text-muted-foreground">
                Partners will use this name when they speak with you.
              </div>
            </div>

            <div class="space-y-2">
              <div class="text-sm font-medium">What is your study major?</div>
              <Input
                v-model="major"
                placeholder="E.g., Computer Science"
                class="w-full"
              />
              <div class="text-xs text-muted-foreground">
                Your partners will be classmates from the same major.
              </div>
            </div>
          </div>

          <div class="space-y-4 border-t pt-4">
            <div class="space-y-1">
              <h3 class="text-sm font-semibold">Personality self-evaluation</h3>
              <p class="text-xs text-muted-foreground">
                These traits help shape who joins your group discussions.
              </p>
            </div>
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div v-for="trait in OCEAN_TRAITS" :key="trait.key" class="space-y-2">
                <div class="space-y-1">
                  <label class="text-sm text-muted-foreground">{{ trait.label }}</label>
                  <div class="text-xs text-muted-foreground">{{ trait.description }}</div>
                </div>
                <Select v-model="oceanModel[trait.key]">
                  <SelectTrigger class="w-full">
                    <SelectValue placeholder="Not set" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem :value="OCEAN_UNSET">Not set</SelectItem>
                    <SelectItem v-for="lvl in OCEAN_LEVELS" :key="lvl" :value="lvl">
                      {{ lvl }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </section>

        <section class="space-y-4 rounded-2xl border border-border/80 bg-muted/30 p-4 sm:p-5">
          <div class="space-y-1">
            <h2 class="text-base font-semibold">English proficiency</h2>
            <p class="text-sm text-muted-foreground">
              Listen to the samples and choose the level that feels comfortable for you.
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>
              Selected level:
              <span class="font-medium text-foreground">
                {{ selectedCefrLevel || authStore.user?.cefr_level || 'Not set yet' }}
              </span>
            </span>
          </div>
          <p
            v-if="authStore.user?.proficiency_reference_utterance"
            class="text-sm text-muted-foreground"
          >
            Your partners adapt to how you speak in discussions.
          </p>

          <Button
            variant="outline"
            class="rounded-xl"
            :disabled="isGeneratingCefr"
            @click="generateCefrSamples"
          >
            {{ isGeneratingCefr ? 'Generating samples…' : 'Generate listening samples' }}
          </Button>

          <div v-if="cefrSampleList.length === 0" class="text-sm text-muted-foreground">
            Generate samples to choose your starting level.
          </div>
          <div v-for="(sample, idx) in cefrSampleList" :key="sample.level" class="rounded-2xl border border-border/80 bg-card p-3">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="flex flex-wrap items-center gap-3">
                <div class="font-medium w-5 text-center">{{ idx + 1 }}</div>
                <div class="font-medium">{{ sample.level }}</div>
                <audio v-if="sample.audio_url" :src="sample.audio_url" controls class="h-8 max-w-[220px]" />
              </div>
              <Button
                class="shrink-0 rounded-xl"
                :variant="selectedCefrLevel === sample.level ? 'default' : 'outline'"
                @click="selectedCefrLevel = sample.level"
              >
                {{ selectedCefrLevel === sample.level ? 'Selected' : 'Choose' }}
              </Button>
            </div>
          </div>
        </section>

        <div v-if="generalError" class="text-destructive text-sm">
          {{ generalError }}
        </div>

        <div class="flex flex-col gap-3">
          <Button
            class="h-11 w-full rounded-xl font-semibold"
            :disabled="isSubmitting"
            @click="handleSave"
          >
            {{ isSubmitting ? 'Saving...' : 'Save' }}
          </Button>
          <Button
            class="h-11 w-full rounded-xl"
            variant="outline"
            :disabled="isSubmitting"
            @click="handleGoToConversation"
          >
            Go to Conversation
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast/use-toast'
import {
  ConversationService,
  PROFILE_ONBOARDING_CEFR_TOPIC,
  type CefrSample,
} from '@/services/conversationService'
import { AuthService } from '@/services/authService'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()
const { toast } = useToast()

const OCEAN_LEVELS = ['low', 'medium', 'high'] as const
const OCEAN_UNSET = '__unset__'
type OceanTraitKey =
  | 'openness'
  | 'conscientiousness'
  | 'extraversion'
  | 'agreeableness'
  | 'neuroticism'

type OceanTraitConfig = {
  key: OceanTraitKey
  label: string
  description: string
}

const OCEAN_TRAITS: OceanTraitConfig[] = [
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

const oceanModel = reactive<Record<OceanTraitKey, string>>({
  openness: authStore.user?.ocean?.openness ?? OCEAN_UNSET,
  conscientiousness: authStore.user?.ocean?.conscientiousness ?? OCEAN_UNSET,
  extraversion: authStore.user?.ocean?.extraversion ?? OCEAN_UNSET,
  agreeableness: authStore.user?.ocean?.agreeableness ?? OCEAN_UNSET,
  neuroticism: authStore.user?.ocean?.neuroticism ?? OCEAN_UNSET,
})

const preferredName = ref(authStore.user?.preferred_name ?? '')
const major = ref(authStore.user?.major ?? '')
const cefrSamples = ref<CefrSample[]>(authStore.user?.cefr_sample_choices ?? [])
const cefrSampleList = computed(() => cefrSamples.value)
const selectedCefrLevel = ref<string | null>(authStore.user?.cefr_level ?? null)
const isGeneratingCefr = ref(false)

const isSubmitting = ref(false)
const generalError = ref<string | null>(null)

function buildOceanPayload(): Record<string, string> {
  const oceanPayload: Record<string, string> = {}
  for (const { key } of OCEAN_TRAITS) {
    const v = oceanModel[key]
    if (v && v !== OCEAN_UNSET) oceanPayload[key] = v
  }
  return oceanPayload
}

function validateProfile(): string | null {
  if (!preferredName.value.trim()) {
    return 'Enter how we should address you.'
  }
  if (!major.value.trim()) {
    return 'Enter your study major.'
  }
  for (const { key, label } of OCEAN_TRAITS) {
    const v = oceanModel[key]
    if (!v || v === OCEAN_UNSET) {
      return `Select a level for ${label}.`
    }
  }
  if (!selectedCefrLevel.value) {
    return 'Choose a CEFR listening level.'
  }
  return null
}

async function persistProfile(): Promise<boolean> {
  const validationError = validateProfile()
  if (validationError) {
    generalError.value = validationError
    toast({
      title: 'Profile incomplete',
      description: validationError,
      variant: 'destructive',
    })
    return false
  }

  const payload = {
    ocean: buildOceanPayload(),
    preferred_name: preferredName.value,
    major: major.value,
    cefr_level: selectedCefrLevel.value,
    cefr_sample_topic: PROFILE_ONBOARDING_CEFR_TOPIC,
    cefr_sample_choices: cefrSamples.value,
  }
  const user = await AuthService.updateUser(payload)
  authStore.user = user
  authStore.saveState()
  return true
}

watch(
  () => authStore.user?.ocean,
  (v) => {
    oceanModel.openness = v?.openness ?? OCEAN_UNSET
    oceanModel.conscientiousness = v?.conscientiousness ?? OCEAN_UNSET
    oceanModel.extraversion = v?.extraversion ?? OCEAN_UNSET
    oceanModel.agreeableness = v?.agreeableness ?? OCEAN_UNSET
    oceanModel.neuroticism = v?.neuroticism ?? OCEAN_UNSET
  },
)

watch(
  () => authStore.user,
  (user) => {
    if (!user) return
    preferredName.value = user.preferred_name ?? ''
    major.value = user.major ?? ''
    selectedCefrLevel.value = user.cefr_level ?? null
    cefrSamples.value = user.cefr_sample_choices ?? []
  },
)

async function generateCefrSamples() {
  isGeneratingCefr.value = true
  selectedCefrLevel.value = null
  try {
    const result = await ConversationService.generateCefrSamples(PROFILE_ONBOARDING_CEFR_TOPIC)
    cefrSamples.value = result.samples
    toast({
      title: 'Samples ready',
      description: 'Listen and choose the level you are comfortable with, then save your profile.',
    })
  } catch (err: unknown) {
    toast({
      title: 'Sample generation failed',
      description: err && typeof err === 'object' && 'message' in err
        ? String((err as { message: string }).message)
        : 'Could not generate CEFR listening samples.',
      variant: 'destructive',
    })
  } finally {
    isGeneratingCefr.value = false
  }
}

async function handleSave() {
  isSubmitting.value = true
  generalError.value = null
  try {
    const saved = await persistProfile()
    if (!saved) return
    toast({
      title: 'Saved',
      description: 'Your profile has been updated.',
    })
  } catch (err: unknown) {
    generalError.value =
      err && typeof err === 'object' && 'message' in err
        ? String((err as { message: string }).message)
        : 'Failed to save profile'
    toast({
      title: 'Error',
      description: generalError.value,
      variant: 'destructive',
    })
  } finally {
    isSubmitting.value = false
  }
}

async function handleGoToConversation() {
  generalError.value = null
  if (!authStore.user?.profile_completed) {
    const validationError = validateProfile()
    generalError.value =
      validationError ?? 'Complete your profile before starting a conversation. Use Save first.'
    toast({
      title: 'Profile incomplete',
      description: generalError.value,
      variant: 'destructive',
    })
    return
  }
  await router.push({ name: 'conversation' })
}
</script>
