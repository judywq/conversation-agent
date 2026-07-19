<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import type { AvatarPreset } from '@/config/avatarPresets'
import { useLive2D } from '@/composables/useLive2D'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  preset: AvatarPreset
  /** Page-level multiplier; per-model zoom readout stays the config value. */
  globalZoom?: number
  /** Shared max export box for Take photo (contain fit). */
  snapshotWidth?: number
  snapshotHeight?: number
}>()

const stageRef = ref<HTMLElement | null>(null)
const {
  status,
  errorMessage,
  capabilities,
  init,
  refit,
  speak,
  playMotion,
  setExpression,
  resetExpression,
  downloadSnapshot,
  dispose,
} = useLive2D(stageRef)

const zoom = ref(props.preset.zoom ?? 2.4)
const testAudioUrl = ref('')
const selectedMotion = ref('')
const motionPlaying = ref(false)
const selectedExpression = ref('')
const fileName = computed(() => props.preset.url.split('/').slice(-3).join('/'))
const zoomLabel = computed(() => zoom.value.toFixed(2))
const activePreset = computed(() => ({
  ...props.preset,
  zoom: zoom.value * (props.globalZoom ?? 1),
}))

const statusLabel = computed(() => {
  if (status.value === 'loading') return 'Loading…'
  if (status.value === 'error') return 'Error'
  if (status.value === 'ready') return 'Ready'
  return 'Not loaded'
})

const motionOptions = computed(() =>
  (capabilities.value?.motionGroups ?? []).flatMap(({ group, motions }) =>
    motions.map((m) => ({
      value: `${group} ${m.index}`,
      label: `${group} · ${m.name}`,
    })),
  ),
)

watch(activePreset, (preset) => {
  if (status.value === 'ready') refit(preset)
})

async function playSelectedMotion() {
  if (!selectedMotion.value || motionPlaying.value) return
  const [group, index] = selectedMotion.value.split(' ')
  motionPlaying.value = true
  try {
    await playMotion(group!, Number(index))
  } finally {
    motionPlaying.value = false
  }
}

function applySelectedExpression() {
  if (selectedExpression.value) void setExpression(selectedExpression.value)
}

async function load(): Promise<boolean> {
  if (status.value === 'ready' || status.value === 'loading') return true
  await nextTick()
  return init(activePreset.value)
}

async function reload() {
  dispose()
  await load()
}

function snapshotFilename(): string {
  const base = props.preset.url.split('/').filter(Boolean).at(-2) ?? 'avatar'
  return `${base}.png`
}

function takePhoto() {
  downloadSnapshot(snapshotFilename(), {
    width: props.snapshotWidth,
    height: props.snapshotHeight,
  })
}

onUnmounted(() => {
  dispose()
})

defineExpose({ load, status })
</script>

<template>
  <div class="rounded-lg border border-border bg-card overflow-hidden">
    <div class="flex items-center justify-between gap-2 border-b px-3 py-2">
      <div class="min-w-0">
        <div class="truncate text-sm font-medium" :title="preset.url">{{ fileName }}</div>
        <div class="text-xs text-muted-foreground">{{ statusLabel }}</div>
      </div>
      <div class="flex shrink-0 items-center gap-1.5">
        <Button
          variant="outline"
          size="sm"
          :disabled="status !== 'ready'"
          @click="takePhoto"
        >
          Take photo
        </Button>
        <Button
          variant="outline"
          size="sm"
          :disabled="status === 'loading'"
          @click="status === 'idle' ? load() : reload()"
        >
          {{ status === 'idle' ? 'Load' : 'Reload' }}
        </Button>
      </div>
    </div>
    <div class="flex items-center gap-2 border-b px-3 py-2">
      <input
        v-model="testAudioUrl"
        placeholder="Audio URL for speak test"
        class="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
      />
      <Button
        variant="outline"
        size="sm"
        :disabled="status !== 'ready' || !testAudioUrl"
        @click="speak(testAudioUrl)"
      >
        Speak
      </Button>
    </div>
    <div v-if="capabilities" class="flex items-center gap-2 border-b px-3 py-2">
      <select
        v-model="selectedMotion"
        class="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
      >
        <option value="" disabled>Motion…</option>
        <option v-for="opt in motionOptions" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <Button
        variant="outline"
        size="sm"
        :disabled="status !== 'ready' || !selectedMotion || motionPlaying"
        @click="playSelectedMotion"
      >
        {{ motionPlaying ? 'Playing…' : 'Play' }}
      </Button>
    </div>
    <div v-if="capabilities && capabilities.expressions.length" class="flex items-center gap-2 border-b px-3 py-2">
      <select
        v-model="selectedExpression"
        class="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
      >
        <option value="" disabled>Expression…</option>
        <option v-for="name in capabilities.expressions" :key="name" :value="name">
          {{ name }}
        </option>
      </select>
      <Button
        variant="outline"
        size="sm"
        :disabled="status !== 'ready' || !selectedExpression"
        @click="applySelectedExpression"
      >
        Apply
      </Button>
      <Button variant="outline" size="sm" :disabled="status !== 'ready'" @click="resetExpression">
        Reset
      </Button>
    </div>
    <div class="flex items-center gap-2 border-b px-3 py-2">
      <span class="shrink-0 text-xs text-muted-foreground">zoom</span>
      <input
        v-model.number="zoom"
        type="range"
        min="0.5"
        max="5"
        step="0.05"
        class="h-8 min-w-0 flex-1 accent-primary"
        aria-label="Zoom"
      />
      <code
        class="w-12 shrink-0 select-all text-right font-mono text-xs tabular-nums"
        :title="'Copy into avatarPresets.ts as zoom: ' + zoomLabel"
      >{{ zoomLabel }}</code>
    </div>
    <div class="relative h-[240px] bg-muted/30">
      <div ref="stageRef" class="absolute inset-0 z-0" />
      <div
        v-if="status === 'idle' || status === 'loading'"
        class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-4 text-center text-xs text-muted-foreground"
      >
        {{ status === 'loading' ? 'Loading avatar…' : 'Not loaded yet' }}
      </div>
      <div
        v-else-if="status === 'error'"
        class="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-destructive"
      >
        {{ errorMessage || 'Avatar unavailable' }}
      </div>
    </div>
  </div>
</template>
