<script setup lang="ts">
import { ChevronDown, Minus } from 'lucide-vue-next'
import { onUnmounted, ref, watch } from 'vue'
import {
  ConversationService,
  type ArgumentSummaryEvidence,
  type ArgumentSummaryResult,
  type ArgumentSummarySpeaker,
} from '@/services/conversationService'

const props = defineProps<{
  sessionId: number | null
  visible: boolean
  /** Turns fully revealed in the UI (excludes agent audio still queued/playing). */
  settledTurnCount: number
  /** Agent turn audio is playing or queued. */
  playbackBusy: boolean
  embedded?: boolean
}>()

const emit = defineEmits<{
  'summary-updated': [summary: ArgumentSummaryResult]
}>()

const summary = ref<ArgumentSummaryResult | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const minimized = ref(false)
const deferredResult = ref<ArgumentSummaryResult | null>(null)

const EVIDENCE_LABELS: Record<string, string> = {
  fact: 'Fact',
  data: 'Data',
  example: 'Example',
}

let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollAttempts = 0
const MAX_POLL_ATTEMPTS = 30
let refreshQueued = false

function clearPollTimer() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function evidenceLabel(type: string): string {
  return EVIDENCE_LABELS[type] || 'Fact'
}

function speakers(result: ArgumentSummaryResult | null): ArgumentSummarySpeaker[] {
  if (!result?.speakers?.length) return []
  return result.speakers
}

function summaryTurnCount(result: ArgumentSummaryResult): number {
  if (typeof result.turn_count === 'number' && Number.isFinite(result.turn_count)) {
    return Math.max(0, Math.floor(result.turn_count))
  }
  return 0
}

function canRevealSummary(result: ArgumentSummaryResult): boolean {
  if (props.playbackBusy) return false
  if (typeof result.turn_count !== 'number') {
    return true
  }
  return summaryTurnCount(result) <= props.settledTurnCount
}

function applySummary(result: ArgumentSummaryResult) {
  summary.value = result
  emit('summary-updated', result)
}

function tryRevealSummary(result: ArgumentSummaryResult): boolean {
  if (!canRevealSummary(result)) {
    deferredResult.value = result
    refreshQueued = true
    return false
  }
  deferredResult.value = null
  refreshQueued = false
  applySummary(result)
  return true
}

function tryApplyDeferred() {
  const pending = deferredResult.value
  if (!pending || !canRevealSummary(pending)) return
  deferredResult.value = null
  refreshQueued = false
  applySummary(pending)
}

function scheduleRefresh() {
  refreshQueued = true
  if (!props.playbackBusy) {
    void loadSummary()
  }
}

function flushQueuedRefresh() {
  if (!refreshQueued || !props.visible || !props.sessionId) return
  if (props.playbackBusy) return
  if (tryApplyDeferred()) {
    return
  }
  refreshQueued = false
  pollAttempts = 0
  void loadSummary()
}

function schedulePendingPoll() {
  if (pollAttempts >= MAX_POLL_ATTEMPTS) return
  pollAttempts += 1
  clearPollTimer()
  pollTimer = setTimeout(() => {
    void loadSummary()
  }, 2000)
}

async function loadSummary() {
  if (!props.sessionId || !props.visible) return
  if (props.playbackBusy) {
    refreshQueued = true
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const result = await ConversationService.fetchArgumentSummary(props.sessionId)
    const revealed = tryRevealSummary(result)

    if (result.status === 'pending' && pollAttempts < MAX_POLL_ATTEMPTS) {
      schedulePendingPoll()
      if (!revealed) {
        loading.value = false
      }
      return
    }

    if (revealed && result.status === 'failed') {
      errorMessage.value = 'Could not generate the argument summary.'
    }
  } catch {
    errorMessage.value = 'Could not load the argument summary.'
  } finally {
    if (summary.value?.status !== 'pending') {
      loading.value = false
    }
  }
}

function resetAndLoad() {
  clearPollTimer()
  pollAttempts = 0
  refreshQueued = false
  deferredResult.value = null
  summary.value = null
  errorMessage.value = ''
  if (props.sessionId && props.visible) {
    void loadSummary()
  } else {
    loading.value = false
  }
}

watch(
  () => [props.sessionId, props.visible] as const,
  () => {
    minimized.value = false
    resetAndLoad()
  },
  { immediate: true },
)

watch(
  () => props.settledTurnCount,
  (count, previous) => {
    if (!props.visible || !props.sessionId) return
    if (previous !== undefined && count > previous) {
      scheduleRefresh()
    }
    tryApplyDeferred()
  },
)

watch(
  () => props.playbackBusy,
  (busy, wasBusy) => {
    if (wasBusy && !busy) {
      flushQueuedRefresh()
    }
    if (!busy) {
      tryApplyDeferred()
    }
  },
)

onUnmounted(() => {
  clearPollTimer()
})
</script>

<template>
  <div
    v-if="visible"
    :class="
      embedded
        ? 'flex h-full min-h-0 flex-col overflow-hidden rounded-lg border bg-background'
        : 'pointer-events-auto fixed bottom-4 left-4 right-4 z-40 sm:left-auto sm:right-4 sm:w-[min(22rem,calc(100vw-2rem))]'
    "
  >
    <div
      :class="
        embedded
          ? 'flex h-full min-h-0 flex-1 flex-col overflow-hidden'
          : 'flex flex-col overflow-hidden rounded-lg border bg-background shadow-lg'
      "
    >
      <div class="flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2">
        <div class="text-sm font-medium">Argument structure</div>
        <button
          type="button"
          class="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          :aria-label="minimized ? 'Expand argument structure' : 'Minimize argument structure'"
          @click="minimized = !minimized"
        >
          <ChevronDown v-if="minimized" class="h-4 w-4" />
          <Minus v-else class="h-4 w-4" />
        </button>
      </div>

      <template v-if="!minimized">
        <p class="shrink-0 border-b px-3 py-1.5 text-[11px] text-muted-foreground">
          Stances by speaker
        </p>

        <div
          :class="
            embedded
              ? 'min-h-0 flex-1 overflow-y-auto px-3 py-2'
              : 'max-h-[min(50vh,28rem)] overflow-y-auto px-3 py-2'
          "
        >
          <div class="space-y-3 text-sm">
            <div v-if="loading && !speakers(summary).length" class="text-muted-foreground">
              Building summary…
            </div>
            <div v-else-if="errorMessage" class="text-destructive">{{ errorMessage }}</div>
            <div v-else-if="summary?.status === 'empty'" class="text-muted-foreground">
              No structured arguments yet.
            </div>
            <template v-else-if="summary?.status === 'ready' || summary?.status === 'pending'">
              <div
                v-if="summary.status === 'pending' && loading"
                class="mb-1 text-[10px] text-muted-foreground"
              >
                Updating…
              </div>
              <div
                v-for="(speaker, speakerIndex) in speakers(summary)"
                :key="`${speaker.speaker_id}-${speakerIndex}`"
                class="space-y-1 border-b pb-2 last:border-b-0 last:pb-0"
              >
                <div class="font-medium leading-snug">{{ speaker.speaker_name || speaker.speaker_id }}</div>
                <div class="text-muted-foreground leading-snug">Stance: {{ speaker.claim }}</div>
                <ul class="list-none space-y-0.5 pl-2">
                  <li
                    v-for="(item, evidenceIndex) in speaker.evidence"
                    :key="`${speaker.speaker_id}-ev-${evidenceIndex}`"
                    class="text-[13px] leading-snug text-muted-foreground"
                  >
                    {{ evidenceLabel((item as ArgumentSummaryEvidence).type) }}:
                    {{ (item as ArgumentSummaryEvidence).text }}
                  </li>
                </ul>
              </div>
              <div
                v-if="!speakers(summary).length && summary.status === 'ready'"
                class="text-muted-foreground"
              >
                No structured arguments yet.
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
