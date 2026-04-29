<template>
  <div class="container mx-auto py-8 px-4">
    <Card class="w-full mx-auto sm:max-w-2xl">
      <CardHeader>
        <CardTitle class="text-2xl">Profile</CardTitle>
        <CardDescription>
          Configure your language-learning profile for the conversation system.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-medium">How should we address you?</div>
          <Input
            v-model="preferredName"
            placeholder="E.g., Alex"
            class="w-full"
          />
          <div class="text-xs text-muted-foreground">
            This name will be used by agents when they speak to you.
          </div>
        </div>

        <div class="rounded-md border p-4 space-y-2">
          <div class="text-sm font-medium">Current proficiency selection</div>
          <div class="text-sm text-muted-foreground">
            Latest selected CEFR level:
            <span class="font-medium text-foreground">{{ authStore.user?.cefr_level || 'Not set yet' }}</span>
          </div>
          <div class="text-sm text-muted-foreground">
            Choose a fresh CEFR listening sample for each new conversation topic before you start.
          </div>
          <div class="text-sm">
            Profile status:
            <span class="font-medium">{{ authStore.user?.profile_completed ? 'Complete' : 'Incomplete' }}</span>
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-sm font-medium">Personality self-evaluation</div>
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

        <div v-if="generalError" class="text-destructive text-sm">
          {{ generalError }}
        </div>

        <Button
          class="w-full"
          :disabled="isSubmitting"
          @click="handleSave"
        >
          {{ isSubmitting ? 'Saving...' : 'Save' }}
        </Button>
      </CardContent>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
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
import { AuthService } from '@/services/authService'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
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

const isSubmitting = ref(false)
const generalError = ref<string | null>(null)

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

async function handleSave() {
  isSubmitting.value = true
  generalError.value = null
  try {
    const oceanPayload: Record<string, string> = {}
    for (const { key } of OCEAN_TRAITS) {
      const v = oceanModel[key]
      if (v && v !== OCEAN_UNSET) oceanPayload[key] = v
    }
    const payload = {
      ocean: oceanPayload,
      preferred_name: preferredName.value,
    }
    const user = await AuthService.updateUser(payload)
    authStore.user = user
    authStore.saveState()
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
</script>
