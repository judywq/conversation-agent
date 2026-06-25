<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronDown } from 'lucide-vue-next'
import AgentAvatarGrid from '@/components/conversation/AgentAvatarGrid.vue'
import ArgumentSummaryPanel from '@/components/conversation/ArgumentSummaryPanel.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast/use-toast'
import { clearAudioBufferCache } from '@/composables/useTalkingHead'
import {
  ConversationService,
  type ArgumentSummaryResult,
  type DiscussionScenarioResult,
  type NewsCategory,
} from '@/services/conversationService'
import {
  ConversationWsClient,
  type ConversationParticipant,
  type ConversationTurn,
  type ConversationWsEvent,
} from '@/services/conversationWs'
import { useAuthStore } from '@/stores/auth'
import { isLipSyncPayload } from '@/types/lipsync'
import {
  buildExportFilename,
  downloadTextFile,
  formatArgumentSummaryText,
  formatCombinedExportText,
  formatTranscriptText,
} from '@/lib/conversationExport'

const { toast } = useToast()
const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const ws = new ConversationWsClient()
const connected = ref(false)
const sessionId = ref<number | null>(null)
const topic = ref('')
const taxonomy = ref<NewsCategory[]>([])
const selectedCategory = ref('')
const selectedSubtopic = ref('')
const isGeneratingScenario = ref(false)
const scenarioArticles = ref<DiscussionScenarioResult['articles']>([])
const MAX_AGENT_COUNT = 3
const agentCount = ref<number>(MAX_AGENT_COUNT)

type Participant = ConversationParticipant

const participants = ref<Participant[]>([])

type Turn = ConversationTurn

const turns = ref<Turn[]>([])
const liveSpeakingTurnKey = ref<string | null>(null)
const completedAgentPlaybackKeys = ref<string[]>([])

function turnKey(turn: Turn): string {
  return `${turn.turn_index}.${turn.subturn_index ?? 0}`
}

function markAgentPlaybackComplete(key: string) {
  if (!completedAgentPlaybackKeys.value.includes(key)) {
    completedAgentPlaybackKeys.value = [...completedAgentPlaybackKeys.value, key]
  }
}

function turnSpeakerLabel(turn: Turn): string {
  if (turn.speaker_display_name) return turn.speaker_display_name
  if (turn.speaker_type === 'user') return 'You'
  return turn.speaker || 'Partner'
}

function markAllAgentPlaybackComplete() {
  for (const turn of turns.value) {
    if (isAgentTurn(turn)) {
      markAgentPlaybackComplete(turnKey(turn))
    }
  }
}

function loadResumedTurns(turnList: Turn[]) {
  turns.value = turnList
  turnPlaybackQueue.value = []
  isProcessingTurnPlayback.value = false
  markAllAgentPlaybackComplete()
}

type TurnDisplayItem = {
  key: string
  turn: Turn | null
  number: number
  showTranscript: boolean
  isCurrent: boolean
  userTurnPrompt: boolean
  statusHint: string
}

function canShowTurnAudioControls(item: TurnDisplayItem): boolean {
  if (!item.turn?.audio_url) return false
  if (liveSpeakingTurnKey.value === item.key) return false
  if (item.turn.speaker_type === 'agent') {
    return completedAgentPlaybackKeys.value.includes(item.key)
  }
  return true
}

function canShowReplayButton(item: TurnDisplayItem): boolean {
  if (!canShowTurnAudioControls(item)) return false
  if (manualReplayTurnKey.value === item.key && manualReplayActive.value && !manualReplayPaused.value) {
    return false
  }
  return true
}

function canShowPauseButton(item: TurnDisplayItem): boolean {
  if (!canShowTurnAudioControls(item)) return false
  return manualReplayTurnKey.value === item.key && manualReplayActive.value && !manualReplayPaused.value
}
const agentStatus = ref<'idle' | 'thinking' | 'finished' | 'searching_online'>('idle')
const activeAgentName = ref('')

const avatarsEnabled = ref(true)
const avatarWarmedUp = ref(false)
const avatarGridRef = ref<InstanceType<typeof AgentAvatarGrid> | null>(null)
const avatarSpeaking = ref(false)
const agentPlaybackBusy = computed(
  () =>
    isProcessingTurnPlayback.value ||
    turnPlaybackQueue.value.length > 0 ||
    avatarSpeaking.value ||
    liveSpeakingTurnKey.value !== null,
)
/** Turns fully revealed: listed turns minus any agent audio still queued or playing. */
const effectiveSettledTurnCount = computed(() => {
  const inFlight =
    turnPlaybackQueue.value.length + (liveSpeakingTurnKey.value ? 1 : 0)
  return Math.max(0, turns.value.length - inFlight)
})
const agentParticipants = computed(() => participants.value.filter((p) => p.type === 'agent'))

function participantRoleLabel(type: Participant['type']): string {
  if (type === 'agent') return 'Discussion partner'
  if (type === 'user') return 'You'
  return type
}
const activeSpeakerId = computed(() => {
  if (liveSpeakingTurnKey.value) {
    const speakingTurn = turns.value.find((t) => turnKey(t) === liveSpeakingTurnKey.value)
    if (speakingTurn?.speaker) return speakingTurn.speaker
  }
  if (agentStatus.value === 'thinking' || agentStatus.value === 'searching_online') {
    const match = participants.value.find(
      (p) => p.type === 'agent' && p.name === activeAgentName.value,
    )
    if (match) return match.id
  }
  const lastAgentTurn = [...turns.value].reverse().find((t) => t.speaker_type === 'agent')
  return lastAgentTurn?.speaker ?? null
})
const pendingTermination = ref<(() => void) | null>(null)
const needUserTurn = ref(false)
const needFirstTurnChoice = ref(false)
const inputText = ref('')
const isPaused = ref(false)
const isEnded = ref(false)
const endedArgumentSummary = ref<ArgumentSummaryResult | null>(null)
const endedSummaryLoading = ref(false)

function onArgumentSummaryUpdated(summary: ArgumentSummaryResult) {
  endedArgumentSummary.value = summary
}

async function fetchEndedArgumentSummary(): Promise<ArgumentSummaryResult | null> {
  if (!sessionId.value) return null
  endedSummaryLoading.value = true
  try {
    const result = await ConversationService.fetchArgumentSummary(sessionId.value)
    endedArgumentSummary.value = result
    return result
  } catch {
    return endedArgumentSummary.value
  } finally {
    endedSummaryLoading.value = false
  }
}

async function resolveEndedArgumentSummary(): Promise<ArgumentSummaryResult | null> {
  const cached = endedArgumentSummary.value
  if (cached?.status === 'ready') {
    return cached
  }
  return fetchEndedArgumentSummary()
}

function downloadTranscript() {
  if (!sessionId.value || turns.value.length === 0) return
  const content = formatTranscriptText(topic.value, turns.value, turnSpeakerLabel)
  downloadTextFile(buildExportFilename(sessionId.value, 'transcript'), content)
}

async function downloadArgumentStructure() {
  if (!sessionId.value) return
  const summary = await resolveEndedArgumentSummary()
  if (!summary || summary.status !== 'ready') return
  const content = formatArgumentSummaryText(summary)
  if (!content) return
  downloadTextFile(buildExportFilename(sessionId.value, 'arguments'), content)
}

async function downloadCombinedExport() {
  if (!sessionId.value || turns.value.length === 0) return
  const summary = await resolveEndedArgumentSummary()
  if (!summary || summary.status !== 'ready') return
  const content = formatCombinedExportText(topic.value, turns.value, turnSpeakerLabel, summary)
  downloadTextFile(buildExportFilename(sessionId.value, 'combined'), content)
}

const canDownloadArgumentStructure = computed(
  () => endedArgumentSummary.value?.status === 'ready' && !!formatArgumentSummaryText(endedArgumentSummary.value),
)

const argumentDownloadBlockedReason = computed(() => {
  if (endedSummaryLoading.value || endedArgumentSummary.value?.status === 'pending') {
    return 'Argument summary is still being generated.'
  }
  if (endedArgumentSummary.value?.status === 'failed') {
    return 'Argument summary could not be generated.'
  }
  if (endedArgumentSummary.value?.status === 'empty') {
    return 'No structured arguments were identified.'
  }
  return ''
})

watch(isEnded, (ended) => {
  if (ended && sessionId.value) {
    void fetchEndedArgumentSummary()
  }
})

const micState = ref<'idle' | 'requesting' | 'recording' | 'preview' | 'transcribing' | 'error'>('idle')
const mediaRecorder = ref<MediaRecorder | null>(null)
const recordedChunks = ref<Blob[]>([])
const recordedBlob = ref<Blob | null>(null)
const recordedUrl = ref<string | null>(null)
const autoSendRecordingAfterStop = ref(false)
const currentAudio = ref<HTMLAudioElement | null>(null)

type TurnPlaybackJob = { turn: Turn }

const turnPlaybackQueue = ref<TurnPlaybackJob[]>([])
const isProcessingTurnPlayback = ref(false)
let playbackAbortController: AbortController | null = null

const showConversationPanel = computed(() => !!sessionId.value || isEnded.value)
const sessionInProgress = computed(() => !!sessionId.value && !isEnded.value)

const turnDisplayList = computed((): TurnDisplayItem[] => {
  const items: TurnDisplayItem[] = turns.value.map((turn, index) => {
    const key = turnKey(turn)
    return {
      key,
      turn,
      number: index + 1,
      showTranscript: turn.speaker_type === 'user',
      isCurrent: liveSpeakingTurnKey.value === key,
      userTurnPrompt: false,
      statusHint: '',
    }
  })

  const userTurnActive =
    needUserTurn.value &&
    !needFirstTurnChoice.value &&
    !isPaused.value &&
    !isProcessingTurnPlayback.value &&
    turnPlaybackQueue.value.length === 0
  const partnerTurnActive =
    sessionInProgress.value &&
    !userTurnActive &&
    !isProcessingTurnPlayback.value &&
    turnPlaybackQueue.value.length === 0 &&
    (agentStatus.value === 'thinking' || agentStatus.value === 'searching_online')

  if (!isEnded.value) {
    if (userTurnActive) {
      items.push({
        key: 'current-turn',
        turn: null,
        number: items.length + 1,
        showTranscript: false,
        isCurrent: true,
        userTurnPrompt: true,
        statusHint: '',
      })
    } else if (partnerTurnActive) {
      items.push({
        key: 'current-turn',
        turn: null,
        number: items.length + 1,
        showTranscript: false,
        isCurrent: true,
        userTurnPrompt: false,
        statusHint: agentStatus.value === 'searching_online' ? 'Checking online…' : 'Thinking…',
      })
    }
  }

  return items
})

const hasCurrentTurnHighlight = computed(() => turnDisplayList.value.some((item) => item.isCurrent))

const turnListScrollRef = ref<HTMLElement | null>(null)

function scrollTurnListToCurrent() {
  void nextTick(() => {
    const container = turnListScrollRef.value
    if (!container || typeof container.querySelector !== 'function') return
    const target =
      container.querySelector<HTMLElement>('[data-turn-current="true"]') ??
      container.querySelector<HTMLElement>('[data-turn-item]:last-of-type')
    target?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

function turnItemClass(isCurrent: boolean): string {
  return isCurrent
    ? 'rounded-md border border-emerald-300 bg-emerald-50/50 px-3 py-2 space-y-1 text-sm'
    : 'border rounded-md p-3 space-y-1'
}

function currentTurnSpeakerLabel(item: TurnDisplayItem): string {
  if (item.userTurnPrompt) return 'You'
  if (item.isCurrent && item.statusHint) return activeAgentName.value || 'A partner'
  if (!item.turn) return ''
  return turnSpeakerLabel(item.turn)
}

watch(
  () => [
    turns.value.length,
    liveSpeakingTurnKey.value,
    agentStatus.value,
    turnDisplayList.value.map((item) => `${item.key}:${item.isCurrent}`).join('|'),
  ],
  () => {
    scrollTurnListToCurrent()
  },
)

const showArgumentSummary = computed(() => !!sessionId.value && turns.value.length > 0)

const canStart = computed(
  () =>
    connected.value &&
    (!sessionId.value || isEnded.value) &&
    !!topic.value.trim() &&
    !!authStore.user?.profile_completed,
)

const availableSubtopics = computed(() => {
  const category = taxonomy.value.find((item) => item.slug === selectedCategory.value)
  return category?.subtopics ?? []
})

const canGenerateScenario = computed(
  () =>
    !!selectedCategory.value &&
    !!selectedSubtopic.value &&
    !isGeneratingScenario.value &&
    (!sessionId.value || isEnded.value),
)

watch(selectedCategory, () => {
  selectedSubtopic.value = ''
})

function nextLocalTurnIndex(): number {
  const lastTurn = turns.value.length > 0 ? turns.value[turns.value.length - 1] : undefined
  const last = lastTurn?.turn_index
  return typeof last === 'number' ? last + 1 : turns.value.length
}

function pushLocalUserTurn(text: string) {
  turns.value.push({
    speaker: 'You',
    speaker_type: 'user',
    utterance: text,
    turn_index: nextLocalTurnIndex(),
  })
}

function clearRecordingPreview() {
  if (recordedUrl.value) URL.revokeObjectURL(recordedUrl.value)
  recordedUrl.value = null
  recordedBlob.value = null
  recordedChunks.value = []
}

function maybeFirePendingTermination() {
  if (!pendingTermination.value) return
  if (isProcessingTurnPlayback.value) return
  if (turnPlaybackQueue.value.length > 0) return
  if (currentAudio.value) return
  if (avatarSpeaking.value) return
  const finalize = pendingTermination.value
  pendingTermination.value = null
  finalize()
}

function flushTurnPlaybackQueueToDisplay() {
  while (turnPlaybackQueue.value.length > 0) {
    const job = turnPlaybackQueue.value.shift()
    if (!job) continue
    turns.value.push(job.turn)
    if (isAgentTurn(job.turn)) {
      markAgentPlaybackComplete(turnKey(job.turn))
    }
  }
}

function stopPlainAudio() {
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value.currentTime = 0
    currentAudio.value = null
  }
}

let manualReplayAbortController: AbortController | null = null
const manualReplayTurnKey = ref<string | null>(null)
const manualReplayPaused = ref(false)
const manualReplayActive = ref(false)

function stopManualTurnAudio() {
  manualReplayAbortController?.abort()
  manualReplayAbortController = null
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value.currentTime = 0
    currentAudio.value = null
  }
  avatarGridRef.value?.setIdleAll?.()
  manualReplayTurnKey.value = null
  manualReplayPaused.value = false
  manualReplayActive.value = false
}

function pauseTurnAudioManual() {
  if (!manualReplayTurnKey.value || manualReplayPaused.value || !manualReplayActive.value) return
  if (currentAudio.value && !currentAudio.value.paused) {
    currentAudio.value.pause()
    manualReplayPaused.value = true
  }
}

async function playTurnAudioManual(turn: Turn, key: string) {
  if (!turn.audio_url) return

  if (manualReplayTurnKey.value === key && manualReplayPaused.value && currentAudio.value) {
    manualReplayPaused.value = false
    manualReplayActive.value = true
    await currentAudio.value.play()
    return
  }

  stopAllAudioPlayback()
  stopManualTurnAudio()

  manualReplayTurnKey.value = key
  manualReplayPaused.value = false
  manualReplayActive.value = true

  const abort = new AbortController()
  manualReplayAbortController = abort

  // Manual replay uses plain audio so pause/resume works reliably (avatar lip-sync has no pause).
  await playPlainAudioAndWait(turn.audio_url, abort.signal)

  manualReplayAbortController = null

  if (abort.signal.aborted) {
    manualReplayActive.value = false
    return
  }

  if (manualReplayPaused.value) {
    return
  }

  manualReplayTurnKey.value = null
  manualReplayActive.value = false
}

function stopAllAudioPlayback() {
  const interruptedKey = liveSpeakingTurnKey.value
  playbackAbortController?.abort()
  playbackAbortController = null
  turnPlaybackQueue.value = []
  isProcessingTurnPlayback.value = false
  liveSpeakingTurnKey.value = null
  if (interruptedKey) {
    const interruptedTurn = turns.value.find((t) => turnKey(t) === interruptedKey)
    if (interruptedTurn && isAgentTurn(interruptedTurn)) {
      markAgentPlaybackComplete(interruptedKey)
    }
  }
  stopManualTurnAudio()
  avatarGridRef.value?.setIdleAll?.()
}

function resetAvatars() {
  avatarGridRef.value?.disposeAll()
  clearAudioBufferCache()
  avatarSpeaking.value = false
}

function warmupAvatars() {
  avatarWarmedUp.value = true
}

async function scheduleAvatarInitialization() {
  if (!avatarsEnabled.value) return
  warmupAvatars()
  await nextTick()
  await avatarGridRef.value?.ensureAllInitialized?.()
  // Child panel refs may register one tick after the grid mounts.
  await nextTick()
  await avatarGridRef.value?.ensureAllInitialized?.()
}

function toggleAvatarsEnabled() {
  avatarsEnabled.value = !avatarsEnabled.value
  if (avatarsEnabled.value) {
    warmupAvatars()
  } else {
    resetAvatars()
  }
}

function isAgentTurn(turn: Turn): boolean {
  return turn.speaker_type === 'agent'
}

async function playAgentTurnAudio(turn: Turn): Promise<boolean> {
  if (!turn.audio_url || !isLipSyncPayload(turn.lipsync)) return false
  if (!avatarsEnabled.value || !avatarWarmedUp.value) return false
  return (await avatarGridRef.value?.speak(turn.speaker, turn.audio_url, turn.lipsync)) ?? false
}

function playPlainAudioAndWait(url: string, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }

    const audio = new Audio(url)
    currentAudio.value = audio

    const finish = () => {
      if (currentAudio.value === audio) {
        currentAudio.value = null
      }
      resolve()
    }

    const onAbort = () => {
      audio.pause()
      audio.currentTime = 0
      if (currentAudio.value === audio) {
        currentAudio.value = null
      }
      resolve()
    }

    signal.addEventListener('abort', onAbort, { once: true })

    audio.onended = () => {
      signal.removeEventListener('abort', onAbort)
      finish()
    }
    audio.onerror = () => {
      signal.removeEventListener('abort', onAbort)
      finish()
    }
    audio.play().catch(() => {
      signal.removeEventListener('abort', onAbort)
      finish()
    })
  })
}

async function playTurnAudioAndWait(turn: Turn, signal: AbortSignal): Promise<void> {
  if (!turn.audio_url || signal.aborted) return

  if (
    isAgentTurn(turn) &&
    avatarsEnabled.value &&
    avatarWarmedUp.value &&
    isLipSyncPayload(turn.lipsync)
  ) {
    const played = await playAgentTurnAudio(turn)
    if (!played && !signal.aborted) {
      await playPlainAudioAndWait(turn.audio_url, signal)
    }
    return
  }

  await playPlainAudioAndWait(turn.audio_url, signal)
}

async function processTurnPlaybackQueue() {
  if (isProcessingTurnPlayback.value) return
  isProcessingTurnPlayback.value = true

  while (turnPlaybackQueue.value.length > 0) {
    const job = turnPlaybackQueue.value.shift()
    if (!job) break

    const key = turnKey(job.turn)
    turns.value.push(job.turn)

    if (!job.turn.audio_url) {
      if (isAgentTurn(job.turn)) {
        markAgentPlaybackComplete(key)
      }
      continue
    }

    const abort = new AbortController()
    playbackAbortController = abort
    avatarSpeaking.value = true
    liveSpeakingTurnKey.value = key

    await playTurnAudioAndWait(job.turn, abort.signal)

    liveSpeakingTurnKey.value = null
    avatarSpeaking.value = false
    playbackAbortController = null

    if (abort.signal.aborted) {
      break
    }

    if (isAgentTurn(job.turn)) {
      markAgentPlaybackComplete(key)
    }
  }

  isProcessingTurnPlayback.value = false
  maybeFirePendingTermination()

  if (turnPlaybackQueue.value.length > 0) {
    void processTurnPlaybackQueue()
  }
}

function enqueueTurnForPlayback(turn: Turn) {
  turnPlaybackQueue.value.push({ turn })
  void processTurnPlaybackQueue()
}

function handleIncomingTurn(turn: Turn) {
  stopManualTurnAudio()

  if (turn.speaker_type === 'user') {
    const existing = [...turns.value].reverse().find((item) => item.speaker_type === 'user')
    if (existing && existing.utterance.trim() === turn.utterance.trim()) {
      if (turn.audio_url) {
        existing.audio_url = turn.audio_url
      }
      if (turn.speaker_display_name) {
        existing.speaker_display_name = turn.speaker_display_name
      }
      return
    }
  }

  enqueueTurnForPlayback(turn)
}

function playAudioNow(url: string) {
  if (!url) return
  const turn = [...turns.value].reverse().find((t) => t.audio_url === url)
  if (!turn?.audio_url) return
  void playTurnAudioManual(turn, turnKey(turn))
}

function handleEvent(e: ConversationWsEvent) {
  if (e.type === 'connected') {
    connected.value = true
  }
  if (e.type === 'session_started') {
    sessionId.value = e.session_id
    // Starting a new session should clear old logs.
    isEnded.value = false
    isPaused.value = false
    needUserTurn.value = false
    needFirstTurnChoice.value = false
    agentStatus.value = 'idle'
    turns.value = []
    turnPlaybackQueue.value = []
    isProcessingTurnPlayback.value = false
    liveSpeakingTurnKey.value = null
    completedAgentPlaybackKeys.value = []
    participants.value = []
    endedArgumentSummary.value = null
    endedSummaryLoading.value = false
    stopAllAudioPlayback()
    resetAvatars()
  }
  if (e.type === 'session_resumed') {
    sessionId.value = e.session_id
    topic.value = e.topic || topic.value
    isEnded.value = false
    isPaused.value = e.paused ?? false
    needFirstTurnChoice.value = false
    needUserTurn.value = e.need_user_turn ?? false
    agentStatus.value = 'idle'
    liveSpeakingTurnKey.value = null
    completedAgentPlaybackKeys.value = []
    participants.value = []
    endedArgumentSummary.value = null
    endedSummaryLoading.value = false
    turnPlaybackQueue.value = []
    isProcessingTurnPlayback.value = false
    stopAllAudioPlayback()
    resetAvatars()
    loadResumedTurns(e.turns ?? [])
    toast({
      title: 'Discussion resumed',
      description: 'Pick up where you left off.',
    })
  }
  if (e.type === 'participants') {
    participants.value = e.participants ?? []
    void scheduleAvatarInitialization()
  }
  if (e.type === 'need_first_turn_choice') {
    needFirstTurnChoice.value = true
    needUserTurn.value = false
  }
  if (e.type === 'paused') {
    isPaused.value = true
    agentStatus.value = 'idle'
  }
  if (e.type === 'resumed') {
    isPaused.value = false
  }
  if (e.type === 'session_ended' || e.type === 'terminated') {
    void authStore.fetchUser().catch(() => {})
    const applyEndedState = () => {
      isEnded.value = true
      isPaused.value = false
      needUserTurn.value = false
      needFirstTurnChoice.value = false
      agentStatus.value = 'idle'
      liveSpeakingTurnKey.value = null
      flushTurnPlaybackQueueToDisplay()
      markAllAgentPlaybackComplete()
    }
    const flushAudio = () => {
      stopAllAudioPlayback()
      flushTurnPlaybackQueueToDisplay()
      avatarGridRef.value?.setIdleAll?.()
      avatarSpeaking.value = false
    }

    if (e.type === 'session_ended') {
      // User-initiated end: stop audio now.
      flushAudio()
      applyEndedState()
    } else {
      // Natural max-turns termination: let the last audio finish before flipping UI state.
      if (
        isProcessingTurnPlayback.value ||
        turnPlaybackQueue.value.length > 0 ||
        currentAudio.value ||
        avatarSpeaking.value
      ) {
        pendingTermination.value = () => {
          flushAudio()
          applyEndedState()
        }
      } else {
        flushAudio()
        applyEndedState()
      }
    }
  }
  if (e.type === 'need_user_turn') {
    isEnded.value = false
    needUserTurn.value = true
    needFirstTurnChoice.value = false
  }
  if (e.type === 'agent_status') {
    agentStatus.value = e.status
    if (e.status === 'searching_online' || e.status === 'thinking') {
      activeAgentName.value = e.agent_display_name ?? ''
    } else {
      activeAgentName.value = ''
    }
  }
  if (e.type === 'turn') {
    isEnded.value = false
    if (e.turn.speaker_type === 'user') needUserTurn.value = false
    handleIncomingTurn(e.turn)
  }
  if (e.type === 'error') {
    toast({ title: 'Error', description: e.message, variant: 'destructive' })
  }
}

function startSession() {
  if (!authStore.user?.profile_completed) return
  warmupAvatars()
  void (async () => {
    try {
      await ws.ready()
      ws.send({ type: 'start_session', topic: topic.value.trim(), agent_count: agentCount.value })
    } catch {
      connected.value = false
      toast({
        title: 'Connection error',
        description: 'Could not connect to the conversation server. Please wait a moment and try again.',
        variant: 'destructive',
      })
    }
  })()
}

function resumeSession(sessionIdToResume: number) {
  warmupAvatars()
  void (async () => {
    try {
      await ws.ready()
      ws.send({ type: 'resume_session', session_id: sessionIdToResume })
    } catch {
      connected.value = false
      toast({
        title: 'Connection error',
        description: 'Could not connect to the conversation server. Please wait a moment and try again.',
        variant: 'destructive',
      })
    }
  })()
}

function volunteer() {
  ws.send({ type: 'raise_hand' })
}

function pauseOrResume() {
  ws.send({ type: isPaused.value ? 'resume' : 'pause' })
}

function stopConversation() {
  if (!sessionId.value) return
  const ok = window.confirm('End the conversation?')
  if (!ok) return
  ws.send({ type: 'end_session' })
}

function sendTextTurn() {
  const text = inputText.value.trim()
  if (!text) return
  pushLocalUserTurn(text)
  ws.send({ type: 'user_turn', utterance: text, source: 'text' })
  inputText.value = ''
  needUserTurn.value = false
}

function chooseFirstTurn(speakFirst: boolean) {
  ws.send({ type: 'first_turn_choice', speak_first: speakFirst })
  needFirstTurnChoice.value = false
  if (speakFirst) {
    needUserTurn.value = true
  } else {
    agentStatus.value = 'thinking'
  }
}

async function startRecording() {
  micState.value = 'requesting'
  clearRecordingPreview()
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    recorder.ondataavailable = (evt) => {
      if (evt.data.size > 0) recordedChunks.value.push(evt.data)
    }
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      const blob = new Blob(recordedChunks.value, { type: 'audio/webm' })
      recordedBlob.value = blob
      recordedUrl.value = URL.createObjectURL(blob)
      if (autoSendRecordingAfterStop.value) {
        autoSendRecordingAfterStop.value = false
        void sendRecording()
      } else {
        micState.value = 'preview'
      }
    }
    recorder.start()
    mediaRecorder.value = recorder
    micState.value = 'recording'
  } catch (err: any) {
    micState.value = 'error'
    toast({
      title: 'Microphone error',
      description: err?.message ?? 'Failed to access microphone',
      variant: 'destructive',
    })
  }
}

function stopRecording() {
  mediaRecorder.value?.stop()
  mediaRecorder.value = null
}

async function sendRecording() {
  if (!recordedBlob.value) return
  micState.value = 'transcribing'
  try {
    const currentSessionId = sessionId.value ? String(sessionId.value) : null
    const [text, upload] = await Promise.all([
      ConversationService.speechToText(recordedBlob.value),
      currentSessionId ? ConversationService.uploadUserAudio(currentSessionId, recordedBlob.value) : Promise.resolve(null),
    ])
    pushLocalUserTurn(text)
    ws.send({
      type: 'user_turn',
      utterance: text,
      source: 'mic',
      audio_url: upload?.audio_url ?? null,
    })
    needUserTurn.value = false
    clearRecordingPreview()
    micState.value = 'idle'
  } catch (err: any) {
    micState.value = 'error'
    toast({
      title: 'Transcription failed',
      description: err?.message ?? 'Failed to transcribe audio',
      variant: 'destructive',
    })
  }
}

function redoRecording() {
  clearRecordingPreview()
  micState.value = 'idle'
}

function toggleRecordingFromKeyboard() {
  if (micState.value === 'recording') {
    autoSendRecordingAfterStop.value = true
    stopRecording()
    return
  }
  if (micState.value !== 'idle' && micState.value !== 'error') {
    return
  }
  if (!needUserTurn.value || needFirstTurnChoice.value) return
  void startRecording()
}

function handleRecordShortcut(event: KeyboardEvent) {
  if (event.code !== 'Space') return
  if (event.repeat) return
  if (event.metaKey || event.ctrlKey || event.altKey) return
  const focused = document.activeElement as HTMLElement | null
  if (focused) {
    const tag = focused.tagName?.toUpperCase()
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON') return
    if (focused.isContentEditable) return
  }
  event.preventDefault()
  toggleRecordingFromKeyboard()
}

function handleConversationInteraction() {
  if (!avatarWarmedUp.value) {
    warmupAvatars()
  }
}

async function loadTaxonomy() {
  try {
    const payload = await ConversationService.fetchNewsTaxonomy()
    taxonomy.value = payload.categories
  } catch (error: any) {
    toast({
      title: 'Could not load topics',
      description: error?.message || 'Please refresh and try again.',
      variant: 'destructive',
    })
  }
}

async function generateDiscussionScenario() {
  if (!selectedCategory.value || !selectedSubtopic.value) return
  isGeneratingScenario.value = true
  try {
    const result = await ConversationService.generateDiscussionScenario(
      selectedCategory.value,
      selectedSubtopic.value,
    )
    topic.value = result.scenario
    scenarioArticles.value = result.articles
    await authStore.fetchUser()
    toast({
      title: 'Scenario ready',
      description: 'You can edit the text below before you start.',
    })
  } catch (error: any) {
    toast({
      title: 'Could not generate scenario',
      description: error?.message || 'Please try again.',
      variant: 'destructive',
    })
  } finally {
    isGeneratingScenario.value = false
  }
}

onMounted(async () => {
  ws.connect()
  const off = ws.onEvent(handleEvent)
  const offConnection = ws.onConnectionChange((open) => {
    if (!open) {
      connected.value = false
    }
  })
  window.addEventListener('keydown', handleRecordShortcut)
  window.addEventListener('pointerdown', handleConversationInteraction, { once: false })
  onUnmounted(() => {
    off()
    offConnection()
  })
  await loadTaxonomy()
  try {
    await authStore.fetchUser()
    selectedCategory.value = authStore.user?.discussion_category?.trim() || ''
    selectedSubtopic.value = authStore.user?.discussion_subtopic?.trim() || ''
    const scenario = authStore.user?.discussion_scenario?.trim()
    if (scenario && !topic.value.trim()) {
      topic.value = scenario
    }
  } catch {
    // Keep the page usable if profile refresh fails.
  }

  const resumeParam = route.query.resume
  const resumeId =
    typeof resumeParam === 'string' ? Number(resumeParam) : Number.NaN
  if (Number.isFinite(resumeId) && resumeId > 0) {
    await router.replace({ name: 'conversation' })
    resumeSession(resumeId)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleRecordShortcut)
  window.removeEventListener('pointerdown', handleConversationInteraction)
  clearRecordingPreview()
  stopAllAudioPlayback()
  resetAvatars()
  connected.value = false
  ws.close()
})
</script>

<template>
  <div class="container mx-auto py-8 px-4 space-y-6">
    <Card>
      <CardHeader>
        <CardTitle>Conversation</CardTitle>
        <CardDescription>
          Choose a topic, set up your discussion group, then start speaking with your partners.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <div class="text-sm font-medium">Major category</div>
            <Select v-model="selectedCategory" :disabled="sessionInProgress || isGeneratingScenario">
              <SelectTrigger class="w-full">
                <SelectValue placeholder="Select a category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="category in taxonomy" :key="category.slug" :value="category.slug">
                  {{ category.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p class="text-xs text-muted-foreground">
              Choose the general subject you want to discuss today.
            </p>
          </div>
          <div class="space-y-2">
            <div class="text-sm font-medium">Subtopic</div>
            <Select
              v-model="selectedSubtopic"
              :disabled="!selectedCategory || sessionInProgress || isGeneratingScenario"
            >
              <SelectTrigger class="w-full">
                <SelectValue placeholder="Select a subtopic" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="subtopic in availableSubtopics"
                  :key="subtopic.slug"
                  :value="subtopic.slug"
                >
                  {{ subtopic.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p class="text-xs text-muted-foreground">
              Pick a specific focus within that subject.
            </p>
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-sm font-medium">Build your scenario</div>
          <p class="text-xs text-muted-foreground">
            Get a suggested prompt for your topic, or write your own in the box below.
          </p>
          <div class="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            :disabled="!canGenerateScenario"
            @click="generateDiscussionScenario"
          >
            {{ isGeneratingScenario ? 'Generating scenario…' : 'Generate scenario' }}
          </Button>
          <p v-if="isGeneratingScenario" class="text-sm text-muted-foreground">
            Preparing your scenario…
          </p>
          <p v-else-if="topic.trim() && scenarioArticles.length" class="text-sm text-muted-foreground">
            Scenario ready—you can edit it below before you start.
          </p>
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-sm font-medium">Discussion scenario</div>
          <Textarea v-model="topic" placeholder="Enter what you would like to discuss…" class="min-h-[80px]" />
        </div>

        <Card class="border">
          <CardHeader>
            <CardTitle class="text-base">Discussion partners</CardTitle>
            <CardDescription>
              Classmates who join you in the discussion.
            </CardDescription>
          </CardHeader>
          <CardContent class="space-y-2">
            <div class="flex items-center gap-3">
              <div class="text-sm font-medium w-36 shrink-0">Number of partners</div>
              <select
                v-model.number="agentCount"
                class="h-9 rounded-md border bg-background px-3 text-sm"
                :disabled="sessionInProgress"
              >
                <option v-for="n in MAX_AGENT_COUNT" :key="n" :value="n">{{ n }}</option>
              </select>
            </div>
            <p class="text-xs text-muted-foreground">
              Choose how many partners join you (1–{{ MAX_AGENT_COUNT }}). More partners means a larger group discussion.
            </p>
            <div v-if="!sessionInProgress" class="pt-2">
              <Button :disabled="!canStart" @click="startSession">Start</Button>
            </div>
          </CardContent>
        </Card>

        <template v-if="showConversationPanel">
        <div class="text-sm text-muted-foreground">
          Status:
          <span v-if="isEnded">Ended</span>
          <span v-else-if="isPaused">Paused</span>
          <span v-else-if="!authStore.user?.profile_completed">Complete your profile first</span>
          <span v-else-if="agentStatus === 'searching_online' || agentStatus === 'thinking'">Waiting…</span>
          <span v-else-if="needFirstTurnChoice">Choose who speaks first</span>
          <span v-else-if="needUserTurn">Your turn</span>
          <span v-else>Idle</span>
        </div>

        <Card v-if="participants.length > 0" class="border">
          <CardHeader>
            <CardTitle class="text-base">Speakers</CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <div class="text-sm text-muted-foreground">
              Here’s everyone in this discussion.
            </div>
            <div v-for="p in participants" :key="p.id" class="flex items-center justify-between rounded-md border px-3 py-2">
              <div class="text-sm">
                <span class="font-medium">{{ p.name }}</span>
                <span class="text-xs text-muted-foreground" v-if="p.type === 'agent' && p.persona_name">
                  · {{ p.persona_name }}
                </span>
                <span class="text-xs text-muted-foreground" v-if="p.type === 'agent' && p.gender">
                  · {{ p.gender }}
                </span>
              </div>
              <div class="text-xs text-muted-foreground">{{ participantRoleLabel(p.type) }}</div>
            </div>
          </CardContent>
        </Card>

        <Card v-if="needFirstTurnChoice && !isEnded" class="border">
          <CardHeader>
            <CardTitle class="text-base">Who speaks first?</CardTitle>
            <CardDescription>
              Decide whether you open the discussion or let one of your partners begin.
            </CardDescription>
          </CardHeader>
          <CardContent class="flex flex-col gap-2 sm:flex-row">
            <Button @click="chooseFirstTurn(true)">I’ll speak first</Button>
            <Button variant="outline" @click="chooseFirstTurn(false)">Let a partner start</Button>
          </CardContent>
        </Card>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            v-if="sessionInProgress && agentParticipants.length > 0"
            variant="outline"
            size="sm"
            @click="toggleAvatarsEnabled"
          >
            {{ avatarsEnabled ? 'Avatars On' : 'Avatars Off' }}
          </Button>
          <span v-if="sessionInProgress && avatarsEnabled && !avatarWarmedUp" class="text-xs text-muted-foreground">
            Click anywhere to show your partners
          </span>
        </div>

        <div
          v-if="agentParticipants.length > 0"
          class="grid grid-cols-1 gap-4"
          :class="
            showArgumentSummary
              ? 'lg:grid-cols-[minmax(360px,28rem)_minmax(12rem,1fr)_minmax(12rem,1fr)] lg:items-stretch lg:gap-3'
              : 'lg:grid-cols-[minmax(360px,28rem)_minmax(0,1fr)]'
          "
        >
          <div class="w-full min-w-[min(100%,360px)] shrink-0 lg:min-w-[360px] lg:max-w-[28rem]">
            <AgentAvatarGrid
              ref="avatarGridRef"
              stacked
              :participants="participants"
              :active-speaker-id="activeSpeakerId"
              :agent-status="agentStatus"
              :warmed-up="avatarWarmedUp && avatarsEnabled"
            />
          </div>

          <div class="min-w-0 space-y-4">
            <Card class="border">
              <CardHeader>
                <CardTitle>Turns</CardTitle>
              </CardHeader>
              <CardContent>
                <div
                  ref="turnListScrollRef"
                  class="max-h-[min(50vh,24rem)] space-y-3 overflow-y-auto lg:max-h-[min(50vh,22rem)]"
                >
                  <div
                    v-if="turnDisplayList.length === 0 && !hasCurrentTurnHighlight"
                    class="text-sm text-muted-foreground"
                  >
                    No turns yet.
                  </div>
                  <div
                    v-for="item in turnDisplayList"
                    :key="item.key"
                    data-turn-item
                    :data-turn-current="item.isCurrent ? 'true' : undefined"
                    :class="turnItemClass(item.isCurrent)"
                  >
                  <div class="text-xs text-muted-foreground">
                    Turn {{ item.number }} ·
                    <span class="font-medium text-foreground">{{ currentTurnSpeakerLabel(item) }}</span>
                  </div>
                  <template v-if="item.userTurnPrompt">
                    <div class="font-medium">Your turn to speak</div>
                    <div class="text-muted-foreground">
                      Use the microphone to respond.
                    </div>
                  </template>
                  <div v-else-if="item.statusHint" class="text-muted-foreground">{{ item.statusHint }}</div>
                  <div v-else-if="item.showTranscript && item.turn" class="whitespace-pre-wrap text-sm">
                    {{ item.turn.utterance }}
                  </div>
                  <div
                    v-if="canShowTurnAudioControls(item)"
                    class="flex flex-wrap gap-2 pt-1"
                  >
                    <Button
                      v-if="canShowReplayButton(item)"
                      variant="outline"
                      size="sm"
                      @click="playTurnAudioManual(item.turn!, item.key)"
                    >
                      Replay
                    </Button>
                    <Button
                      v-if="canShowPauseButton(item)"
                      variant="outline"
                      size="sm"
                      @click="pauseTurnAudioManual"
                    >
                      Pause
                    </Button>
                  </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <template v-if="!isEnded">
            <div class="grid grid-cols-1 gap-3">
              <Card class="border">
                <CardHeader>
                  <CardTitle class="text-base">Speak (microphone)</CardTitle>
                </CardHeader>
                <CardContent class="space-y-3">
                  <div class="text-sm text-muted-foreground">Mic state: {{ micState }}</div>
                  <div class="flex gap-2">
                    <Button
                      :disabled="
                        !needUserTurn ||
                        needFirstTurnChoice ||
                        micState === 'recording' ||
                        micState === 'preview' ||
                        micState === 'transcribing'
                      "
                      @click="startRecording"
                    >
                      Record
                    </Button>
                    <Button variant="outline" :disabled="micState !== 'recording'" @click="stopRecording">
                      Stop
                    </Button>
                  </div>
                  <div class="text-xs text-muted-foreground">
                    You may also press
                    <kbd class="mx-0.5 rounded border bg-muted px-1.5 py-0.5 font-mono text-[0.7rem]">Space</kbd>
                    to start or stop recording.
                  </div>

                  <div v-if="micState === 'preview' && recordedUrl" class="space-y-2 rounded-md border p-3">
                    <div class="text-sm font-medium">Preview recording</div>
                    <audio :src="recordedUrl" controls class="w-full" />
                    <div class="flex flex-col gap-2 sm:flex-row">
                      <Button :disabled="!needUserTurn || needFirstTurnChoice" @click="sendRecording">Send</Button>
                      <Button variant="outline" @click="redoRecording">Redo</Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t">
              <Button variant="destructive" @click="stopConversation">
                End
              </Button>
            </div>
            </template>
          </div>

          <ArgumentSummaryPanel
            embedded
            class="h-[min(50vh,24rem)] max-h-[min(50vh,24rem)] min-h-0"
            :session-id="sessionId"
            :settled-turn-count="effectiveSettledTurnCount"
            :playback-busy="agentPlaybackBusy"
            :visible="showArgumentSummary"
            @summary-updated="onArgumentSummaryUpdated"
          />
        </div>

        <template v-else>
        <div
          class="grid grid-cols-1 gap-4"
          :class="showArgumentSummary ? 'lg:grid-cols-[minmax(12rem,1fr)_minmax(12rem,1fr)] lg:items-stretch lg:gap-3' : ''"
        >
        <div class="min-w-0 space-y-4">
        <Card class="border">
          <CardHeader>
            <CardTitle>Turns</CardTitle>
          </CardHeader>
          <CardContent>
            <div
              ref="turnListScrollRef"
              class="max-h-[min(50vh,24rem)] space-y-3 overflow-y-auto"
            >
              <div
                v-if="turnDisplayList.length === 0 && !hasCurrentTurnHighlight"
                class="text-sm text-muted-foreground"
              >
                No turns yet.
              </div>
              <div
                v-for="item in turnDisplayList"
                :key="item.key"
                data-turn-item
                :data-turn-current="item.isCurrent ? 'true' : undefined"
                :class="turnItemClass(item.isCurrent)"
              >
              <div class="text-xs text-muted-foreground">
                Turn {{ item.number }} ·
                <span class="font-medium text-foreground">{{ currentTurnSpeakerLabel(item) }}</span>
              </div>
              <template v-if="item.userTurnPrompt">
                <div class="font-medium">Your turn to speak</div>
                <div class="text-muted-foreground">
                  Use the microphone to respond.
                </div>
              </template>
              <div v-else-if="item.statusHint" class="text-muted-foreground">{{ item.statusHint }}</div>
              <div v-else-if="item.showTranscript && item.turn" class="whitespace-pre-wrap text-sm">
                {{ item.turn.utterance }}
              </div>
              <div
                v-if="canShowTurnAudioControls(item)"
                class="flex flex-wrap gap-2 pt-1"
              >
                <Button
                  v-if="canShowReplayButton(item)"
                  variant="outline"
                  size="sm"
                  @click="playTurnAudioManual(item.turn!, item.key)"
                >
                  Replay
                </Button>
                <Button
                  v-if="canShowPauseButton(item)"
                  variant="outline"
                  size="sm"
                  @click="pauseTurnAudioManual"
                >
                  Pause
                </Button>
              </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <template v-if="!isEnded">
        <div class="grid grid-cols-1 gap-3">
          <Card class="border">
            <CardHeader>
              <CardTitle class="text-base">Speak (microphone)</CardTitle>
            </CardHeader>
            <CardContent class="space-y-3">
              <div class="text-sm text-muted-foreground">Mic state: {{ micState }}</div>
              <div class="flex gap-2">
                <Button
                  :disabled="
                    !needUserTurn ||
                    needFirstTurnChoice ||
                    micState === 'recording' ||
                    micState === 'preview' ||
                    micState === 'transcribing'
                  "
                  @click="startRecording"
                >
                  Record
                </Button>
                <Button variant="outline" :disabled="micState !== 'recording'" @click="stopRecording">
                  Stop
                </Button>
              </div>
              <div class="text-xs text-muted-foreground">
                You may also press
                <kbd class="mx-0.5 rounded border bg-muted px-1.5 py-0.5 font-mono text-[0.7rem]">Space</kbd>
                to start or stop recording.
              </div>

              <div v-if="micState === 'preview' && recordedUrl" class="space-y-2 rounded-md border p-3">
                <div class="text-sm font-medium">Preview recording</div>
                <audio :src="recordedUrl" controls class="w-full" />
                <div class="flex flex-col gap-2 sm:flex-row">
                  <Button :disabled="!needUserTurn || needFirstTurnChoice" @click="sendRecording">Send</Button>
                  <Button variant="outline" @click="redoRecording">Redo</Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div class="flex flex-wrap gap-2 pt-2 border-t">
          <Button variant="destructive" @click="stopConversation">
            End
          </Button>
        </div>
        </template>
        </div>

        <ArgumentSummaryPanel
          v-if="sessionId"
          embedded
          class="h-[min(50vh,24rem)] max-h-[min(50vh,24rem)] min-h-0"
          :session-id="sessionId"
          :settled-turn-count="effectiveSettledTurnCount"
          :playback-busy="agentPlaybackBusy"
          :visible="showArgumentSummary"
          @summary-updated="onArgumentSummaryUpdated"
        />
        </div>
        </template>

        <details v-if="isEnded && turns.length > 0" class="group rounded-md border">
          <summary
            class="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-base font-medium [&::-webkit-details-marker]:hidden"
          >
            <span>Full transcript</span>
            <ChevronDown class="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div class="space-y-4 border-t px-4 py-3">
            <div v-for="(turn, index) in turns" :key="turnKey(turn)" class="space-y-1">
              <div class="text-xs text-muted-foreground">
                Turn {{ index + 1 }} ·
                <span class="font-medium text-foreground">{{ turnSpeakerLabel(turn) }}</span>
              </div>
              <div class="whitespace-pre-wrap text-sm">{{ turn.utterance }}</div>
            </div>
          </div>
        </details>

        <div v-if="isEnded && turns.length > 0" class="space-y-2">
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" @click="downloadTranscript">
              Download transcript
            </Button>
            <Button
              variant="outline"
              size="sm"
              :disabled="!canDownloadArgumentStructure"
              @click="downloadArgumentStructure"
            >
              Download argument structure
            </Button>
            <Button
              variant="outline"
              size="sm"
              :disabled="!canDownloadArgumentStructure"
              @click="downloadCombinedExport"
            >
              Download both
            </Button>
          </div>
          <p v-if="argumentDownloadBlockedReason" class="text-xs text-muted-foreground">
            {{ argumentDownloadBlockedReason }}
          </p>
        </div>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
