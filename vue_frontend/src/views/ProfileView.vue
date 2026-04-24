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
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <label class="text-sm font-medium">CEFR level</label>
            <Select v-model="cefrLevelModel">
              <SelectTrigger class="w-full">
                <SelectValue placeholder="Not set" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem :value="CEFR_UNSET">Not set</SelectItem>
                <SelectItem v-for="lvl in CEFR_LEVELS" :key="lvl" :value="lvl">
                  {{ lvl }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-sm font-medium">OCEAN self-evaluation</div>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div v-for="trait in OCEAN_TRAITS" :key="trait.key" class="space-y-2">
              <label class="text-sm text-muted-foreground">{{ trait.label }}</label>
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

const CEFR_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'] as const
const CEFR_UNSET = '__unset__'
const cefrLevelModel = ref<string>(
  authStore.user?.cefr_level && authStore.user.cefr_level.length > 0
    ? authStore.user.cefr_level
    : CEFR_UNSET,
)

const OCEAN_LEVELS = ['low', 'medium', 'high'] as const
const OCEAN_UNSET = '__unset__'
type OceanTraitKey =
  | 'openness'
  | 'conscientiousness'
  | 'extraversion'
  | 'agreeableness'
  | 'neuroticism'

const OCEAN_TRAITS = [
  { key: 'openness', label: 'Openness' },
  { key: 'conscientiousness', label: 'Conscientiousness' },
  { key: 'extraversion', label: 'Extraversion' },
  { key: 'agreeableness', label: 'Agreeableness' },
  { key: 'neuroticism', label: 'Neuroticism' },
] as const satisfies ReadonlyArray<{ key: OceanTraitKey; label: string }>

const oceanModel = reactive<Record<OceanTraitKey, string>>({
  openness: authStore.user?.ocean?.openness ?? OCEAN_UNSET,
  conscientiousness: authStore.user?.ocean?.conscientiousness ?? OCEAN_UNSET,
  extraversion: authStore.user?.ocean?.extraversion ?? OCEAN_UNSET,
  agreeableness: authStore.user?.ocean?.agreeableness ?? OCEAN_UNSET,
  neuroticism: authStore.user?.ocean?.neuroticism ?? OCEAN_UNSET,
})

const isSubmitting = ref(false)
const generalError = ref<string | null>(null)

watch(
  () => authStore.user?.cefr_level,
  (v) => {
    cefrLevelModel.value = v && v.length > 0 ? v : CEFR_UNSET
  },
)
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
      cefr_level: cefrLevelModel.value === CEFR_UNSET ? (null as null) : cefrLevelModel.value,
      ocean: oceanPayload,
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
