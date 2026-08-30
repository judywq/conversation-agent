<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import type { AvatarPreset } from '@/config/avatarPresets'
import { AVATAR_DEFAULT_ZOOM, resolveAvatarOffset } from '@/config/avatarPresets'
import {
  LIVE2D_GESTURES_LIST,
  gesturesForUrl,
  resolveGestureMotion,
  type Live2DGesture,
} from '@/config/live2dGestures'
import { useLive2D } from '@/composables/useLive2D'
import { Button } from '@/components/ui/button'
import { Camera } from 'lucide-vue-next'

const props = defineProps<{
  preset: AvatarPreset
  /** Page-level multiplier; per-model zoom readout stays the config value. */
  globalZoom?: number
  /** Shared Live2D stage CSS size (framing / aspect). */
  stageWidth?: number
  stageHeight?: number
  /** Multiplier on stage CSS size for Take photo (1 = Stage W×H pixels). */
  snapshotRatio?: number
  /** Delay before capture, in seconds. */
  snapshotDelaySec?: number
  /** When true, model tracks the mouse cursor. */
  lookAtCursor?: boolean
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
  stopMotion,
  setExpression,
  resetExpression,
  downloadSnapshot,
  setAutoFocus,
  dispose,
} = useLive2D(stageRef)

// Use AVATAR_DEFAULT_ZOOM instead of hardcoded default
const zoom = ref(props.preset.zoom ?? AVATAR_DEFAULT_ZOOM)
const offsetX = ref(props.preset.offsetX ?? 0)
const offsetY = ref(props.preset.offsetY ?? 0)
const testAudioUrl = ref('')
const selectedGesture = ref<Live2DGesture>('idle')
const gestureIndex = ref(0)
const selectedMotion = ref('')
const motionPlaying = ref(false)
const selectedExpression = ref('')
/** Remaining countdown seconds while waiting to snap; null when idle. */
const photoCountdown = ref<number | null>(null)
let photoTimer: ReturnType<typeof setInterval> | null = null
let photoTimeout: ReturnType<typeof setTimeout> | null = null

const fileName = computed(() => props.preset.url.split('/').slice(-3).join('/'))
const zoomLabel = computed(() => zoom.value.toFixed(2))
const offsetXLabel = computed(() => String(Math.round(offsetX.value)))
const offsetYLabel = computed(() => String(Math.round(offsetY.value)))
const activePreset = computed(() => ({
  ...props.preset,
  zoom: zoom.value * (props.globalZoom ?? 1),
  ...resolveAvatarOffset(offsetX.value, offsetY.value),
}))
const photoBusy = computed(() => photoCountdown.value != null)
const photoCountdownLabel = computed(() => {
  const t = photoCountdown.value
  if (t == null) return null
  return String(Math.max(1, Math.ceil(t)))
})

const stageStyle = computed(() => {
  const w = props.stageWidth
  const h = props.stageHeight
  return {
    width: `${Number.isFinite(w) && (w as number) > 0 ? w : 360}px`,
    height: `${Number.isFinite(h) && (h as number) > 0 ? h : 240}px`,
  }
})

const statusLabel = computed(() => {
  if (status.value === 'loading') return 'Loading…'
  if (status.value === 'error') return 'Error'
  if (status.value === 'ready') return 'Ready'
  return 'Not loaded'
})

const gestureMap = computed(() => gesturesForUrl(props.preset.url))
const gestureNames = computed(() => gestureMap.value?.[selectedGesture.value] ?? [])
const gestureMaxIndex = computed(() => Math.max(0, gestureNames.value.length - 1))
const gestureResolved = computed(() => {
  if (!capabilities.value || !gestureMap.value) return null
  return resolveGestureMotion(
    capabilities.value,
    gestureMap.value,
    selectedGesture.value,
    gestureIndex.value,
  )
})

const motionOptions = computed(() =>
  (capabilities.value?.motionGroups ?? []).flatMap(({ group, motions }) =>
    motions.map((m) => ({
      value: `${group} ${m.index}`,
      label: `${group} · ${m.name}`,
    })),
  ),
)

watch(selectedGesture, () => {
  if (gestureIndex.value > gestureMaxIndex.value) gestureIndex.value = 0
})

watch(activePreset, (preset) => {
  if (status.value === 'ready') refit(preset)
})

watch(
  () => props.lookAtCursor,
  (enabled) => {
    if (status.value === 'ready') setAutoFocus(enabled !== false)
  },
)

async function playSelectedGesture() {
  if (motionPlaying.value) {
    stopMotion()
    return
  }
  const resolved = gestureResolved.value
  if (!resolved) return
  motionPlaying.value = true
  try {
    await playMotion(resolved.group, resolved.index)
  } finally {
    motionPlaying.value = false
  }
}

async function playSelectedMotion() {
  if (motionPlaying.value) {
    stopMotion()
    return
  }
  if (!selectedMotion.value) return
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
  return init(activePreset.value, { autoFocus: props.lookAtCursor !== false })
}

async function reload() {
  dispose()
  await load()
}

function snapshotFilename(): string {
  const base = props.preset.url.split('/').filter(Boolean).at(-2) ?? 'avatar'
  return `${base}.png`
}

function clearPhotoTimers() {
  if (photoTimer != null) {
    clearInterval(photoTimer)
    photoTimer = null
  }
  if (photoTimeout != null) {
    clearTimeout(photoTimeout)
    photoTimeout = null
  }
  photoCountdown.value = null
}

function takePhoto() {
  if (status.value !== 'ready' || photoBusy.value) return

  const delaySec = Math.max(0, Number(props.snapshotDelaySec) || 0)
  if (delaySec <= 0) {
    downloadSnapshot(snapshotFilename(), props.snapshotRatio ?? 1)
    return
  }

  const started = performance.now()
  const delayMs = delaySec * 1000
  photoCountdown.value = delaySec

  photoTimer = setInterval(() => {
    const left = delaySec - (performance.now() - started) / 1000
    photoCountdown.value = left > 0 ? left : 0
  }, 100)

  photoTimeout = setTimeout(() => {
    clearPhotoTimers()
    if (status.value === 'ready') {
      downloadSnapshot(snapshotFilename(), props.snapshotRatio ?? 1)
    }
  }, delayMs)
}

onUnmounted(() => {
  clearPhotoTimers()
  dispose()
})

function getSettings() {
  return {
    url: props.preset.url,
    zoom: zoom.value,
    offsetX: offsetX.value,
    offsetY: offsetY.value,
  }
}

function applySettings(partial: { zoom?: number; offsetX?: number; offsetY?: number }) {
  if (typeof partial.zoom === 'number' && Number.isFinite(partial.zoom)) {
    zoom.value = partial.zoom
  }
  if (typeof partial.offsetX === 'number' && Number.isFinite(partial.offsetX)) {
    offsetX.value = partial.offsetX
  }
  if (typeof partial.offsetY === 'number' && Number.isFinite(partial.offsetY)) {
    offsetY.value = partial.offsetY
  }
}

defineExpose({ load, status, getSettings, applySettings })
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
          class="min-w-9 px-2"
          :disabled="status !== 'ready' || photoBusy"
          :aria-label="photoBusy ? `Capturing in ${photoCountdownLabel}` : 'Take photo'"
          @click="takePhoto"
        >
          <span
            v-if="photoBusy"
            class="w-4 text-center font-mono text-xs tabular-nums"
          >{{ photoCountdownLabel }}</span>
          <Camera v-else class="h-4 w-4" aria-hidden="true" />
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
        v-model="selectedGesture"
        class="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
        :disabled="!gestureMap"
      >
        <option v-for="g in LIVE2D_GESTURES_LIST" :key="g" :value="g">
          {{ g }}{{ gestureMap ? ` (${gestureMap[g].length})` : '' }}
        </option>
      </select>
      <input
        v-model.number="gestureIndex"
        type="number"
        min="0"
        :max="gestureMaxIndex"
        step="1"
        class="h-8 w-14 shrink-0 rounded-md border border-input bg-background px-2 text-xs tabular-nums"
        aria-label="Gesture motion index"
        :disabled="!gestureMap || gestureNames.length === 0"
      />
      <Button
        variant="outline"
        size="sm"
        :disabled="status !== 'ready' || (!motionPlaying && !gestureResolved)"
        :title="
          motionPlaying
            ? 'Stop motion'
            : gestureResolved
              ? gestureResolved.name
              : 'No motion for this gesture/index'
        "
        @click="playSelectedGesture"
      >
        {{ motionPlaying ? 'Stop' : 'Play' }}
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
        :disabled="status !== 'ready' || (!motionPlaying && !selectedMotion)"
        @click="playSelectedMotion"
      >
        {{ motionPlaying ? 'Stop' : 'Play' }}
      </Button>
    </div>
    <div v-if="capabilities" class="flex items-center gap-2 border-b px-3 py-2">
      <select
        v-model="selectedExpression"
        class="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs"
        :disabled="!capabilities.expressions.length"
      >
        <option value="" disabled>
          {{ capabilities.expressions.length ? 'Expression…' : 'No expressions' }}
        </option>
        <option v-for="name in capabilities.expressions" :key="name" :value="name">
          {{ name }}
        </option>
      </select>
      <Button
        variant="outline"
        size="sm"
        :disabled="status !== 'ready' || !selectedExpression || !capabilities.expressions.length"
        @click="applySelectedExpression"
      >
        Apply
      </Button>
      <Button
        variant="outline"
        size="sm"
        :disabled="status !== 'ready' || !capabilities.expressions.length"
        @click="resetExpression"
      >
        Reset
      </Button>
    </div>
    <div class="flex items-center gap-2 border-b px-3 py-2">
      <span class="shrink-0 text-xs text-muted-foreground">zoom</span>
      <input
        v-model.number="zoom"
        type="range"
        min="0.1"
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
    <div class="flex items-center gap-2 border-b px-3 py-2">
      <span class="shrink-0 text-xs text-muted-foreground">x</span>
      <input
        v-model.number="offsetX"
        type="range"
        min="-200"
        max="200"
        step="1"
        class="h-8 min-w-0 flex-1 accent-primary"
        aria-label="Offset X"
      />
      <code
        class="w-12 shrink-0 select-all text-right font-mono text-xs tabular-nums"
        :title="'Copy into avatarPresets.ts as offsetX: ' + offsetXLabel"
      >{{ offsetXLabel }}</code>
    </div>
    <div class="flex items-center gap-2 border-b px-3 py-2">
      <span class="shrink-0 text-xs text-muted-foreground">y</span>
      <input
        v-model.number="offsetY"
        type="range"
        min="-200"
        max="200"
        step="1"
        class="h-8 min-w-0 flex-1 accent-primary"
        aria-label="Offset Y"
      />
      <code
        class="w-12 shrink-0 select-all text-right font-mono text-xs tabular-nums"
        :title="'Copy into avatarPresets.ts as offsetY: ' + offsetYLabel"
      >{{ offsetYLabel }}</code>
    </div>
    <div class="flex justify-center overflow-auto bg-muted/30 p-2">
      <div class="relative shrink-0 bg-muted/40" :style="stageStyle">
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
  </div>
</template>
