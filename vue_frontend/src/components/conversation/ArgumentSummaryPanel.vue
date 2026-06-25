<script setup lang="ts">
import { ChevronDown, Minus } from 'lucide-vue-next'
import { onUnmounted, ref, watch } from 'vue'
import {
  explanationLabel,
  explanationLine,
  speakersFromSummary,
} from '@/lib/argumentSummaryDisplay'
import {
  ConversationService,
  type ArgumentSummaryResult,
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

function tryApplyDeferred(): boolean {
  const pending = deferredResult.value
  if (!pending || !canRevealSummary(pending)) return false
  deferredResult.value = null
  refreshQueued = false
  applySummary(pending)
  return true
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
  } catch {
    errorMessage.value = 'Could not load speaker opinions.'
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
        <div class="text-sm font-medium">Speaker opinions</div>
        <button
          type="button"
          class="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          :aria-label="minimized ? 'Expand speaker opinions' : 'Minimize speaker opinions'"
          @click="minimized = !minimized"
        >
          <ChevronDown v-if="minimized" class="h-4 w-4" />
          <Minus v-else class="h-4 w-4" />
        </button>
      </div>

      <template v-if="!minimized">
        <div
          :class="
            embedded
              ? 'min-h-0 flex-1 overflow-y-auto px-3 py-2'
              : 'max-h-[min(50vh,28rem)] overflow-y-auto px-3 py-2'
          "
        >
          <div class="space-y-3 text-sm">
            <div v-if="loading && !speakersFromSummary(summary).length" class="text-muted-foreground">
              Building summary…
            </div>
            <div v-else-if="errorMessage" class="text-destructive">{{ errorMessage }}</div>
            <div v-else-if="summary?.status === 'empty' || summary?.status === 'failed'" class="text-muted-foreground">
              No speaker opinions yet.
            </div>
            <template v-else-if="summary?.status === 'ready' || summary?.status === 'pending'">
              <div
                v-if="summary.status === 'pending' && loading"
                class="mb-1 text-[10px] text-muted-foreground"
              >
                Updating…
              </div>
              <div
                v-for="(speaker, speakerIndex) in speakersFromSummary(summary)"
                :key="`${speaker.speaker_id}-${speakerIndex}`"
                class="space-y-2 border-b pb-2 last:border-b-0 last:pb-0"
              >
                <div class="font-medium leading-snug">{{ speaker.speaker_name || speaker.speaker_id }}</div>
                <div
                  v-for="(claim, claimIndex) in speaker.claims"
                  :key="`${speaker.speaker_id}-claim-${claimIndex}`"
                  class="space-y-1 pl-2"
                >
                  <div class="leading-snug">{{ claim.text }}</div>
                  <ul
                    v-for="(reason, reasonIndex) in claim.reasons || []"
                    :key="`${speaker.speaker_id}-reason-${claimIndex}-${reasonIndex}`"
                    class="space-y-0.5 pl-2"
                  >
                    <li class="text-[12px] leading-snug text-muted-foreground">
                      {{ reason.text }}
                    </li>
                    <li
                      v-for="(explanation, explanationIndex) in reason.explanations || []"
                      :key="`${speaker.speaker_id}-exp-${claimIndex}-${reasonIndex}-${explanationIndex}`"
                      class="truncate pl-2 text-[11px] leading-snug text-muted-foreground"
                      :title="explanationLine(explanation)"
                    >
                      {{ explanationLabel(explanation.type) }}: {{ explanation.text }}
                    </li>
                  </ul>
                </div>
              </div>
              <div
                v-if="!speakersFromSummary(summary).length && summary.status === 'ready'"
                class="text-muted-foreground"
              >
                No speaker opinions yet.
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
