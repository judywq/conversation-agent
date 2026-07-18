<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { avatarPresetForAgent } from '@/config/avatarPresets'
import { useLive2D } from '@/composables/useLive2D'
import type { LipSyncPayload } from '@/types/lipsync'

const props = defineProps<{
  agentId: string
  name: string
  gender?: string
  live2dUrl?: string
  index: number
  active: boolean
  agentStatus?: 'idle' | 'thinking' | 'finished' | 'searching_online'
  warmedUp: boolean
  /** Immersive game-phase rendering: no card chrome/header, stage fills the parent. */
  game?: boolean
  /** Shared-stage layout (game mode): total slot columns and this agent's column. */
  slotCount?: number
  slotIndex?: number
  /** Multiplier on the preset zoom, from the user size slider. */
  zoomScale?: number
}>()

const stageRef = ref<HTMLElement | null>(null)
const { status, errorMessage, init, refit, speak, setIdle, dispose } = useLive2D(stageRef)

const preset = computed(() => {
  const base = props.live2dUrl
    ? { url: props.live2dUrl }
    : avatarPresetForAgent(props.gender, props.index)
  return {
    ...base,
    zoom: (base.zoom ?? 2.4) * (props.zoomScale ?? 1),
    slots: props.slotCount,
    slot: props.slotIndex,
  }
})

watch(preset, (p) => refit(p))

const statusLabel = computed(() => {
  if (props.agentStatus === 'searching_online' && props.active) {
    return 'Checking online…'
  }
  if (props.agentStatus === 'thinking' && props.active) {
    return 'Thinking…'
  }
  if (status.value === 'loading') return 'Loading avatar…'
  if (status.value === 'error') return 'Avatar unavailable'
  if (status.value === 'speaking') return 'Speaking…'
  if (status.value === 'ready') return 'Ready'
  if (props.warmedUp) return 'Loading avatar…'
  return 'Waiting for warmup'
})

async function ensureInit() {
  if (!props.warmedUp) return
  if (status.value === 'ready' || status.value === 'loading') return
  await nextTick()
  if (!stageRef.value) return
  await init(preset.value)
}

watch(
  () => props.live2dUrl,
  () => {
    dispose()
    void ensureInit()
  },
)

watch(
  () => props.warmedUp,
  (ready) => {
    if (ready) void ensureInit()
  },
)

onMounted(() => {
  void ensureInit()
})

onUnmounted(() => {
  dispose()
})

async function speakTurn(audioUrl: string, lipsync: LipSyncPayload): Promise<boolean> {
  await ensureInit()
  if (status.value === 'error') return false
  return speak(audioUrl, lipsync)
}

defineExpose({
  speakTurn,
  setIdle,
  dispose,
  ensureInit,
  status,
})
</script>

<template>
  <div
    :class="
      game
        ? 'h-full'
        : [
            'overflow-hidden rounded-lg border bg-card transition-shadow',
            active ? 'border-primary shadow-md ring-1 ring-primary/30' : 'border-border',
          ]
    "
    :aria-label="`${name} avatar`"
  >
    <div v-if="!game" class="flex items-center justify-between gap-2 border-b px-3 py-2">
      <div class="min-w-0">
        <div class="truncate text-sm font-medium">{{ name }}</div>
        <div class="truncate text-xs text-muted-foreground">{{ statusLabel }}</div>
      </div>
      <span
        v-if="active"
        class="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary"
      >
        Active
      </span>
    </div>
    <div class="relative" :class="game ? 'h-full' : 'h-[240px] bg-muted/30'">
      <div ref="stageRef" class="absolute inset-0 z-0" />
      <div
        v-if="status === 'idle' || status === 'loading'"
        class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-4 text-center text-xs text-muted-foreground"
      >
        {{ warmedUp ? 'Loading avatar…' : 'Click anywhere in the conversation to enable avatars' }}
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
