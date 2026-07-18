<template>
  <div class="space-y-6">
    <Stepper
      v-slot="{ isPrevDisabled, modelValue }"
      v-model="stepIndex"
      class="block w-full"
    >
      <div class="flex w-full items-start gap-2">
        <StepperItem
          v-for="(step, index) in steps"
          :key="step.step"
          v-slot="{ state }"
          class="relative flex w-full flex-col items-center justify-center"
          :step="step.step"
        >
          <StepperSeparator
            v-if="step.step !== steps[steps.length - 1]?.step"
            class="absolute left-[calc(50%+20px)] right-[calc(-50%+10px)] top-5 block h-0.5 shrink-0 rounded-full bg-muted group-data-[state=completed]:bg-primary"
          />

          <StepperTrigger as-child>
            <Button
              type="button"
              :variant="state === 'completed' || state === 'active' ? 'default' : 'outline'"
              size="icon"
              class="z-10 shrink-0 rounded-full"
              :class="[state === 'active' && 'ring-2 ring-ring ring-offset-2 ring-offset-background']"
              :disabled="state !== 'completed' && index + 1 > (modelValue || 1)"
            >
              <Check v-if="state === 'completed'" class="size-5" />
              <Circle v-else-if="state === 'active'" class="size-5" />
              <Dot v-else class="size-5" />
            </Button>
          </StepperTrigger>

          <div class="mt-5 flex flex-col items-center text-center">
            <StepperTitle
              :class="[state === 'active' && 'text-primary']"
              class="text-sm font-semibold transition lg:text-base"
            >
              {{ step.title }}
            </StepperTitle>
            <StepperDescription
              :class="[state === 'active' && 'text-primary']"
              class="sr-only text-xs text-muted-foreground transition md:not-sr-only lg:text-sm"
            >
              {{ step.description }}
            </StepperDescription>
          </div>
        </StepperItem>
      </div>

      <div class="mt-6 space-y-4">
        <template v-if="stepIndex === 1">
          <div class="space-y-1">
            <h2 class="text-base font-semibold">About you</h2>
            <p class="text-sm text-muted-foreground">
              Your name and study background help your discussion partners get to know you.
            </p>
          </div>
          <div class="space-y-2">
            <div class="text-sm font-medium">How should we address you?</div>
            <Input v-model="preferredName" placeholder="E.g., Alex" class="w-full" />
            <div class="text-xs text-muted-foreground">
              Partners will use this name when they speak with you.
            </div>
          </div>
          <div class="space-y-2">
            <div class="text-sm font-medium">What is your study major?</div>
            <Input v-model="major" placeholder="E.g., Computer Science" class="w-full" />
            <div class="text-xs text-muted-foreground">
              Your partners will be classmates from the same major.
            </div>
          </div>
        </template>

        <template v-else-if="stepIndex === 2">
          <div class="space-y-1">
            <h2 class="text-base font-semibold">Personality self-evaluation</h2>
            <p class="text-sm text-muted-foreground">
              These traits help shape who joins your group discussions.
            </p>
          </div>
          <OceanTraitsFields ref="oceanFieldsRef" :model-value="oceanModel" />
        </template>

        <template v-else>
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
          <Button
            variant="outline"
            type="button"
            :disabled="isGeneratingCefr"
            @click="generateCefrSamples"
          >
            {{ isGeneratingCefr ? 'Generating samples…' : 'Generate listening samples' }}
          </Button>
          <div v-if="cefrSamples.length === 0" class="text-sm text-muted-foreground">
            Generate samples to choose your starting level.
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
        </template>
      </div>

      <div v-if="generalError" class="mt-4 text-sm text-destructive">
        {{ generalError }}
      </div>

      <div class="mt-6 flex items-center justify-between gap-3">
        <Button
          type="button"
          variant="outline"
          :disabled="isPrevDisabled || isSubmitting"
          @click="goPrev"
        >
          Back
        </Button>
        <Button
          type="button"
          class="font-semibold"
          :disabled="isSubmitting"
          @click="handlePrimaryAction"
        >
          {{
            isSubmitting
              ? 'Saving…'
              : stepIndex === 3
                ? 'Finish'
                : 'Next'
          }}
        </Button>
      </div>
    </Stepper>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { Check, Circle, Dot } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import OceanTraitsFields from '@/components/profile/OceanTraitsFields.vue'
import {
  Stepper,
  StepperDescription,
  StepperItem,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from '@/components/ui/stepper'
import { useToast } from '@/components/ui/toast/use-toast'
import {
  aboutPayload,
  cefrPayload,
  emptyOceanModel,
  firstIncompleteStep,
  oceanPayload,
  type ProfileStep,
  validateStep,
} from '@/lib/profileForm'
import {
  ConversationService,
  PROFILE_ONBOARDING_CEFR_TOPIC,
  type CefrSample,
} from '@/services/conversationService'
import { AuthService } from '@/services/authService'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const { toast } = useToast()

const steps = [
  { step: 1, title: 'About you', description: 'Name and major' },
  { step: 2, title: 'Personality', description: 'OCEAN traits' },
  { step: 3, title: 'English', description: 'Listening level' },
]

const stepIndex = ref<ProfileStep>(firstIncompleteStep(authStore.user))
const preferredName = ref(authStore.user?.preferred_name ?? '')
const major = ref(authStore.user?.major ?? '')
const oceanModel = reactive(emptyOceanModel(authStore.user))
const oceanFieldsRef = ref<InstanceType<typeof OceanTraitsFields> | null>(null)
const cefrSamples = ref<CefrSample[]>(authStore.user?.cefr_sample_choices ?? [])
const selectedCefrLevel = ref<string | null>(authStore.user?.cefr_level ?? null)
const isGeneratingCefr = ref(false)
const isSubmitting = ref(false)
const generalError = ref<string | null>(null)

function formState() {
  return {
    preferredName: preferredName.value,
    major: major.value,
    ocean: oceanModel,
    selectedCefrLevel: selectedCefrLevel.value,
    cefrSamples: cefrSamples.value,
  }
}

function goPrev() {
  if (stepIndex.value <= 1) return
  stepIndex.value = (stepIndex.value - 1) as ProfileStep
}

async function persistCurrentStep(): Promise<boolean> {
  const step = stepIndex.value

  if (step === 2) {
    const oceanValues = await oceanFieldsRef.value?.validateAndApply()
    if (!oceanValues) {
      generalError.value = null
      return false
    }
    Object.assign(oceanModel, oceanValues)
  } else {
    const validationError = validateStep(step, formState())
    if (validationError) {
      generalError.value = validationError
      toast({
        title: 'Profile incomplete',
        description: validationError,
        variant: 'destructive',
      })
      return false
    }
  }

  const payload =
    step === 1
      ? aboutPayload(formState())
      : step === 2
        ? oceanPayload(formState())
        : cefrPayload(formState(), PROFILE_ONBOARDING_CEFR_TOPIC)

  const user = await AuthService.updateUser(payload)
  authStore.user = user
  authStore.saveState()
  return true
}

async function handlePrimaryAction() {
  isSubmitting.value = true
  generalError.value = null
  try {
    const saved = await persistCurrentStep()
    if (!saved) return
    if (stepIndex.value < 3) {
      // Advance after persist; do not also sync step from authStore.user mid-wizard
      // (that would double-advance if a watcher also called firstIncompleteStep).
      stepIndex.value = Math.min(3, stepIndex.value + 1) as ProfileStep
      toast({
        title: 'Saved',
        description: 'Continuing to the next step.',
      })
      return
    }
    toast({
      title: 'Profile complete',
      description: 'Your profile has been saved.',
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
      description: 'Listen and choose the level you are comfortable with, then finish.',
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
