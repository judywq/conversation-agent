<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { avatarPresetForAgent, type AvatarBody } from '@/config/avatarPresets'
import { useTalkingHead } from '@/composables/useTalkingHead'
import type { LipSyncPayload } from '@/types/lipsync'

const props = defineProps<{
  agentId: string
  name: string
  gender?: string
  index: number
  active: boolean
  agentStatus?: 'idle' | 'thinking' | 'finished' | 'searching_online'
  warmedUp: boolean
}>()

const stageRef = ref<HTMLElement | null>(null)
const { status, errorMessage, init, speak, setIdle, dispose } = useTalkingHead(stageRef)

const preset = computed(() => avatarPresetForAgent(props.gender, props.index))

const statusLabel = computed(() => {
  if (status.value === 'loading') return 'Loading avatar…'
  if (status.value === 'error') return 'Avatar unavailable'
  if (props.agentStatus === 'searching_online' && props.active) return 'Checking online…'
  if (props.agentStatus === 'thinking' && props.active) return 'Thinking…'
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
  await init(preset.value.url, preset.value.body as AvatarBody)
}

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
    class="rounded-lg border bg-card overflow-hidden transition-shadow"
    :class="active ? 'border-primary shadow-md ring-1 ring-primary/30' : 'border-border'"
    :aria-label="`${name} avatar`"
  >
    <div class="flex items-center justify-between gap-2 border-b px-3 py-2">
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
    <div class="relative h-[240px] bg-muted/30">
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
