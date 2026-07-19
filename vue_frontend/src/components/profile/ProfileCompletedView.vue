<template>
  <div class="space-y-6">
    <!-- About you -->
    <section class="space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-base font-semibold">About you</h2>
          <p class="text-sm text-muted-foreground">
            Your name and study background.
          </p>
        </div>
        <Button
          v-if="editingSection !== 'about'"
          type="button"
          variant="outline"
          size="sm"
          :disabled="editingSection !== null"
          @click="startEdit('about')"
        >
          Edit
        </Button>
      </div>

      <template v-if="editingSection === 'about'">
        <AvatarPicker v-model="avatarId" />
        <div class="space-y-2">
          <div class="text-sm font-medium">How should we address you?</div>
          <Input v-model="preferredName" placeholder="E.g., Alex" class="w-full" />
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium">What is your study major?</div>
          <Input v-model="major" placeholder="E.g., Computer Science" class="w-full" />
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            :disabled="isSubmitting"
            @click="saveSection('about')"
          >
            {{ isSubmitting ? 'Saving…' : 'Save' }}
          </Button>
          <Button
            type="button"
            variant="outline"
            :disabled="isSubmitting"
            @click="cancelEdit"
          >
            Cancel
          </Button>
        </div>
      </template>
      <dl v-else class="grid gap-3 text-sm sm:grid-cols-2">
        <div class="sm:col-span-2 flex items-center gap-3">
          <img
            v-if="currentAvatar"
            :src="currentAvatar.url"
            :alt="currentAvatar.label"
            class="h-14 w-14 rounded-full object-cover border border-border"
          />
          <div
            v-else
            class="flex h-14 w-14 items-center justify-center rounded-full border border-border bg-muted text-muted-foreground"
          >
            —
          </div>
          <div>
            <dt class="text-muted-foreground">Avatar</dt>
            <dd class="font-medium text-foreground">
              {{ currentAvatar?.label || 'Not set' }}
            </dd>
          </div>
        </div>
        <div>
          <dt class="text-muted-foreground">Preferred name</dt>
          <dd class="font-medium text-foreground">
            {{ authStore.user?.preferred_name || 'Not set' }}
          </dd>
        </div>
        <div>
          <dt class="text-muted-foreground">Major</dt>
          <dd class="font-medium text-foreground">
            {{ authStore.user?.major || 'Not set' }}
          </dd>
        </div>
      </dl>
    </section>

    <div class="border-t" />

    <!-- Personality -->
    <section class="space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-base font-semibold">Personality</h2>
          <p class="text-sm text-muted-foreground">
            Your OCEAN self-evaluation.
          </p>
        </div>
        <Button
          v-if="editingSection !== 'ocean'"
          type="button"
          variant="outline"
          size="sm"
          :disabled="editingSection !== null"
          @click="startEdit('ocean')"
        >
          Edit
        </Button>
      </div>

      <template v-if="editingSection === 'ocean'">
        <OceanTraitsFields ref="oceanFieldsRef" :model-value="oceanModel" />
        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            :disabled="isSubmitting"
            @click="saveSection('ocean')"
          >
            {{ isSubmitting ? 'Saving…' : 'Save' }}
          </Button>
          <Button
            type="button"
            variant="outline"
            :disabled="isSubmitting"
            @click="cancelEdit"
          >
            Cancel
          </Button>
        </div>
      </template>
      <dl v-else class="grid gap-3 text-sm sm:grid-cols-2">
        <div v-for="trait in OCEAN_TRAITS" :key="trait.key">
          <dt class="text-muted-foreground">{{ trait.label }}</dt>
          <dd class="font-medium capitalize text-foreground">
            {{ authStore.user?.ocean?.[trait.key] || 'Not set' }}
          </dd>
        </div>
      </dl>
    </section>

    <div class="border-t" />

    <!-- English proficiency -->
    <section class="space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-base font-semibold">English proficiency</h2>
          <p class="text-sm text-muted-foreground">
            Your CEFR listening level.
          </p>
        </div>
        <Button
          v-if="editingSection !== 'cefr'"
          type="button"
          variant="outline"
          size="sm"
          :disabled="editingSection !== null"
          @click="startEdit('cefr')"
        >
          Edit
        </Button>
      </div>

      <template v-if="editingSection === 'cefr'">
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>
            Selected level:
            <span class="font-medium text-foreground">
              {{ selectedCefrLevel || 'Not set yet' }}
            </span>
          </span>
        </div>
        <Button
          type="button"
          variant="outline"
          :disabled="isGeneratingCefr"
          @click="generateCefrSamples"
        >
          {{ isGeneratingCefr ? 'Generating samples…' : 'Generate listening samples' }}
        </Button>
        <div v-if="cefrSamples.length === 0" class="text-sm text-muted-foreground">
          Generate samples to choose your level, or keep your current selection.
        </div>
        <div
          v-for="(sample, idx) in cefrSamples"
          :key="sample.level"
          class="rounded-2xl border border-border/80 bg-card/40 p-3 backdrop-blur-sm"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex flex-wrap items-center gap-3">
              <div class="w-5 text-center font-medium">{{ idx + 1 }}</div>
              <div class="font-medium">{{ sample.level }}</div>
              <audio
                v-if="sample.audio_url"
                :src="sample.audio_url"
                controls
                class="h-8 max-w-[220px]"
              />
            </div>
            <Button
              type="button"
              class="shrink-0"
              :variant="selectedCefrLevel === sample.level ? 'default' : 'outline'"
              @click="selectedCefrLevel = sample.level"
            >
              {{ selectedCefrLevel === sample.level ? 'Selected' : 'Choose' }}
            </Button>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            :disabled="isSubmitting"
            @click="saveSection('cefr')"
          >
            {{ isSubmitting ? 'Saving…' : 'Save' }}
          </Button>
          <Button
            type="button"
            variant="outline"
            :disabled="isSubmitting"
            @click="cancelEdit"
          >
            Cancel
          </Button>
        </div>
      </template>
      <div v-else class="space-y-2 text-sm">
        <div>
          <span class="text-muted-foreground">Selected level: </span>
          <span class="font-medium text-foreground">
            {{ authStore.user?.cefr_level || 'Not set' }}
          </span>
        </div>
        <p
          v-if="authStore.user?.proficiency_reference_utterance"
          class="text-muted-foreground"
        >
          Your partners adapt to how you speak in discussions.
        </p>
      </div>
    </section>

    <div v-if="generalError" class="text-sm text-destructive">
      {{ generalError }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import AvatarPicker from '@/components/profile/AvatarPicker.vue'
import OceanTraitsFields from '@/components/profile/OceanTraitsFields.vue'
import { useToast } from '@/components/ui/toast/use-toast'
import {
  aboutPayload,
  cefrPayload,
  emptyOceanModel,
  OCEAN_TRAITS,
  oceanPayload,
  validateStep,
} from '@/lib/profileForm'
import { profileAvatarById } from '@/config/profileAvatars'
import {
  ConversationService,
  PROFILE_ONBOARDING_CEFR_TOPIC,
  type CefrSample,
} from '@/services/conversationService'
import { AuthService } from '@/services/authService'
import { useAuthStore } from '@/stores/auth'

type EditSection = 'about' | 'ocean' | 'cefr'

const authStore = useAuthStore()
const { toast } = useToast()

const editingSection = ref<EditSection | null>(null)
const preferredName = ref(authStore.user?.preferred_name ?? '')
const major = ref(authStore.user?.major ?? '')
const avatarId = ref(authStore.user?.avatar_id ?? '')
const oceanModel = reactive(emptyOceanModel(authStore.user))
const oceanFieldsRef = ref<InstanceType<typeof OceanTraitsFields> | null>(null)
const cefrSamples = ref<CefrSample[]>(authStore.user?.cefr_sample_choices ?? [])
const selectedCefrLevel = ref<string | null>(authStore.user?.cefr_level ?? null)
const isGeneratingCefr = ref(false)
const isSubmitting = ref(false)
const generalError = ref<string | null>(null)

const currentAvatar = computed(() => profileAvatarById(authStore.user?.avatar_id))

function syncFromUser() {
  const user = authStore.user
  preferredName.value = user?.preferred_name ?? ''
  major.value = user?.major ?? ''
  avatarId.value = user?.avatar_id ?? ''
  Object.assign(oceanModel, emptyOceanModel(user))
  selectedCefrLevel.value = user?.cefr_level ?? null
  cefrSamples.value = user?.cefr_sample_choices ?? []
}

watch(
  () => authStore.user,
  () => {
    if (editingSection.value) return
    syncFromUser()
  },
)

function formState() {
  return {
    preferredName: preferredName.value,
    major: major.value,
    avatarId: avatarId.value,
    ocean: oceanModel,
    selectedCefrLevel: selectedCefrLevel.value,
    cefrSamples: cefrSamples.value,
  }
}

function startEdit(section: EditSection) {
  syncFromUser()
  editingSection.value = section
  generalError.value = null
}

function cancelEdit() {
  syncFromUser()
  editingSection.value = null
  generalError.value = null
}

async function saveSection(section: EditSection) {
  if (section === 'ocean') {
    const oceanValues = await oceanFieldsRef.value?.validateAndApply()
    if (!oceanValues) {
      generalError.value = null
      return
    }
    Object.assign(oceanModel, oceanValues)
  } else {
    const step = section === 'about' ? 1 : 3
    const validationError = validateStep(step, formState())
    if (validationError) {
      generalError.value = validationError
      toast({
        title: 'Profile incomplete',
        description: validationError,
        variant: 'destructive',
      })
      return
    }
  }

  isSubmitting.value = true
  generalError.value = null
  try {
    const payload =
      section === 'about'
        ? aboutPayload(formState())
        : section === 'ocean'
          ? oceanPayload(formState())
          : cefrPayload(formState(), PROFILE_ONBOARDING_CEFR_TOPIC)

    const user = await AuthService.updateUser(payload)
    authStore.user = user
    authStore.saveState()
    editingSection.value = null
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

async function generateCefrSamples() {
  isGeneratingCefr.value = true
  selectedCefrLevel.value = null
  try {
    const result = await ConversationService.generateCefrSamples(PROFILE_ONBOARDING_CEFR_TOPIC)
    cefrSamples.value = result.samples
    toast({
      title: 'Samples ready',
      description: 'Listen and choose the level you are comfortable with, then save.',
    })
  } catch (err: unknown) {
    toast({
      title: 'Sample generation failed',
      description:
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message: string }).message)
          : 'Could not generate CEFR listening samples.',
      variant: 'destructive',
    })
  } finally {
    isGeneratingCefr.value = false
  }
}
</script>
