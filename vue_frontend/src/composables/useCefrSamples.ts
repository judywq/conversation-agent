import { computed, onUnmounted, ref, type Ref } from 'vue'
import {
  ConversationService,
  type CefrSample,
  type CefrSamplesStatus,
} from '@/services/conversationService'

const POLL_INTERVAL_MS = 2000

export function useCefrSamples(options: {
  cefrSamples: Ref<CefrSample[]>
  status: Ref<CefrSamplesStatus>
  onReady?: () => void
  onFailed?: (message: string) => void
}) {
  const isStarting = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let notifyOnTerminal = false

  const isGenerating = computed(
    () => isStarting.value || options.status.value === 'pending',
  )
  const hasSamples = computed(() => options.cefrSamples.value.length > 0)

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function applyResult(result: {
    status: CefrSamplesStatus
    samples: CefrSample[]
  }) {
    options.status.value = result.status
    if (result.samples.length > 0) {
      options.cefrSamples.value = result.samples
    } else if (result.status === 'pending' || result.status === 'failed') {
      options.cefrSamples.value = []
    }
  }

  function handleTerminal(status: CefrSamplesStatus) {
    if (!notifyOnTerminal) return
    notifyOnTerminal = false
    if (status === 'ready') {
      options.onReady?.()
    } else if (status === 'failed') {
      options.onFailed?.('Could not generate CEFR listening samples.')
    }
  }

  async function refreshOnce() {
    const result = await ConversationService.fetchCefrSamples()
    applyResult(result)
    if (result.status === 'ready' || result.status === 'failed') {
      stopPolling()
      handleTerminal(result.status)
    }
    return result
  }

  function startPolling() {
    stopPolling()
    notifyOnTerminal = true
    pollTimer = setInterval(() => {
      void refreshOnce().catch(() => {
        /* keep polling; transient network errors */
      })
    }, POLL_INTERVAL_MS)
  }

  async function startGeneration(topic: string) {
    const trimmed = topic.trim()
    if (!trimmed) {
      throw new Error('Topic is required to generate listening samples.')
    }
    isStarting.value = true
    options.cefrSamples.value = []
    options.status.value = 'pending'
    notifyOnTerminal = true
    try {
      const result = await ConversationService.startCefrSamples(trimmed)
      applyResult(result)
      if (result.status === 'pending') {
        startPolling()
      } else if (result.status === 'ready' || result.status === 'failed') {
        handleTerminal(result.status)
      }
      return result
    } finally {
      isStarting.value = false
    }
  }

  async function syncFromServer() {
    const result = await refreshOnce()
    if (result.status === 'pending') {
      startPolling()
    }
    return result
  }

  onUnmounted(() => {
    stopPolling()
  })

  return {
    isGenerating,
    hasSamples,
    startGeneration,
    syncFromServer,
    stopPolling,
  }
}
