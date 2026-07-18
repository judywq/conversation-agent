<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import {
  BookOpen,
  Check,
  FolderOpen,
  Loader2,
  LogOut,
  Mic,
  NotebookPen,
  Settings,
  Smartphone,
  Square,
} from 'lucide-vue-next'
import AgentAvatarGrid from '@/components/conversation/AgentAvatarGrid.vue'
import ArgumentSummaryPanel from '@/components/conversation/ArgumentSummaryPanel.vue'
import PartnerSelectPanel from '@/components/conversation/PartnerSelectPanel.vue'
import SakuraCorner from '@/components/SakuraCorner.vue'
import SakuraMark from '@/components/SakuraMark.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast/use-toast'
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
import { hideAppNav } from '@/composables/useLayoutChrome'
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
const wsSessionBound = ref(false)
const wsReconnecting = ref(false)
let pendingSilentResumeSessionId: number | null = null
let sessionResumePromise: Promise<void> | null = null
let wsWaitCancel: (() => void) | null = null
const SESSION_RESUME_TIMEOUT_MS = 10000
const sessionId = ref<number | null>(null)
const sessionMaxTurns = ref(0)
const sessionTurnCount = ref(0)
const topic = ref('')
const taxonomy = ref<NewsCategory[]>([])
const selectedCategory = ref('')
const selectedSubtopic = ref('')
const isGeneratingScenario = ref(false)
const scenarioArticles = ref<DiscussionScenarioResult['articles']>([])
const MAX_AGENT_COUNT = 3
const selectedCharacterIds = ref<string[]>([])

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

const agentStatus = ref<'idle' | 'thinking' | 'finished' | 'searching_online'>('idle')
const activeAgentName = ref('')

const avatarsEnabled = useStorage('conv-game-avatars', true)
const showSpeechBubble = useStorage('conv-game-show-bubble', true)
const avatarScale = useStorage('conv-game-avatar-scale', 1)

const SCENE_OPTIONS = [
  { id: 'classroom', label: 'Sunny Classroom', url: '/scenes/classroom.png' },
  { id: 'library', label: 'Library Terrace', url: '/scenes/library.png' },
  { id: 'campus-cafe', label: 'Campus Café', url: '/scenes/campus-cafe.png' },
  { id: 'sports-ground', label: 'Sports Ground', url: '/scenes/sports-ground.png' },
  { id: 'meeting-room', label: 'Meeting Room', url: '/scenes/meeting-room.png' },
  { id: 'outdoors', label: 'Outdoors', url: '/scenes/outdoors.png' },
  { id: 'pathway', label: 'Pathway', url: '/scenes/pathway.png' },
] as const

type SceneId = (typeof SCENE_OPTIONS)[number]['id']

function randomSceneId(): SceneId {
  return SCENE_OPTIONS[Math.floor(Math.random() * SCENE_OPTIONS.length)].id
}

const sceneId = useStorage<SceneId>('conv-game-scene', randomSceneId())
const sceneBlur = useStorage('conv-game-scene-blur', 4)
const sceneUrl = computed(
  () => SCENE_OPTIONS.find((s) => s.id === sceneId.value)?.url ?? SCENE_OPTIONS[0].url,
)
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
const userTurnsAllowed = computed(
  () => {
    const count = Math.max(sessionTurnCount.value, turns.value.length)
    return sessionMaxTurns.value <= 0 || count < sessionMaxTurns.value
  },
)
const canStartMic = computed(
  () =>
    needUserTurn.value &&
    !needFirstTurnChoice.value &&
    userTurnsAllowed.value &&
    !agentPlaybackBusy.value &&
    agentStatus.value !== 'thinking' &&
    agentStatus.value !== 'searching_online',
)
/** Turns fully revealed: listed turns minus any agent audio still queued or playing. */
const effectiveSettledTurnCount = computed(() => {
  const inFlight =
    turnPlaybackQueue.value.length + (liveSpeakingTurnKey.value ? 1 : 0)
  return Math.max(0, turns.value.length - inFlight)
})
const agentParticipants = computed(() => participants.value.filter((p) => p.type === 'agent'))

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

let endedSummaryPollTimer: ReturnType<typeof setTimeout> | null = null
let endedSummaryPollAttempts = 0
const MAX_ENDED_SUMMARY_POLL_ATTEMPTS = 30
const ENDED_SUMMARY_POLL_INTERVAL_MS = 2000

function clearEndedSummaryPollTimer() {
  if (endedSummaryPollTimer !== null) {
    clearTimeout(endedSummaryPollTimer)
    endedSummaryPollTimer = null
  }
}

function isEndedSummaryTerminal(status: ArgumentSummaryResult['status'] | undefined): boolean {
  return status === 'ready' || status === 'failed' || status === 'empty'
}

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

function scheduleEndedSummaryPoll() {
  if (endedSummaryPollAttempts >= MAX_ENDED_SUMMARY_POLL_ATTEMPTS) return
  endedSummaryPollAttempts += 1
  clearEndedSummaryPollTimer()
  endedSummaryPollTimer = setTimeout(() => {
    void pollEndedArgumentSummary()
  }, ENDED_SUMMARY_POLL_INTERVAL_MS)
}

async function pollEndedArgumentSummary(): Promise<ArgumentSummaryResult | null> {
  if (!sessionId.value) return null
  const result = await fetchEndedArgumentSummary()
  if (!result || isEndedSummaryTerminal(result.status)) {
    clearEndedSummaryPollTimer()
    return result
  }
  scheduleEndedSummaryPoll()
  return result
}

function startEndedArgumentSummaryPolling() {
  if (!sessionId.value) return
  clearEndedSummaryPollTimer()
  endedSummaryPollAttempts = 0
  void pollEndedArgumentSummary()
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
  if (endedArgumentSummary.value?.status === 'failed' || endedArgumentSummary.value?.status === 'empty') {
    return 'No speaker opinions were identified.'
  }
  return ''
})

watch(isEnded, (ended) => {
  if (ended && sessionId.value) {
    startEndedArgumentSummaryPolling()
  } else {
    clearEndedSummaryPollTimer()
    endedSummaryPollAttempts = 0
  }
})

const micState = ref<'idle' | 'requesting' | 'recording' | 'preview' | 'transcribing' | 'error'>('idle')
const mediaRecorder = ref<MediaRecorder | null>(null)
const recordedChunks = ref<Blob[]>([])
const recordedBlob = ref<Blob | null>(null)
const recordedUrl = ref<string | null>(null)
const pendingMicSend = ref<{ text: string; audioUrl: string | null } | null>(null)
const autoSendRecordingAfterStop = ref(false)
/** `performance.now()` when MediaRecorder started; used to enforce a 1s minimum. */
let recordingStartedAt: number | null = null
const MIN_RECORDING_MS = 1000
const currentAudio = ref<HTMLAudioElement | null>(null)

type TurnPlaybackJob = { turn: Turn }

const turnPlaybackQueue = ref<TurnPlaybackJob[]>([])
const isProcessingTurnPlayback = ref(false)
let playbackAbortController: AbortController | null = null

const showConversationPanel = computed(() => !!sessionId.value || isEnded.value)
const sessionInProgress = computed(() => !!sessionId.value && !isEnded.value)

watch(
  showConversationPanel,
  (immersive) => {
    hideAppNav.value = immersive
  },
  { immediate: true },
)

const showArgumentSummary = computed(() => !!sessionId.value && turns.value.length > 0)

const canStart = computed(
  () =>
    connected.value &&
    (!sessionId.value || isEnded.value) &&
    !!topic.value.trim() &&
    selectedCharacterIds.value.length >= 1 &&
    selectedCharacterIds.value.length <= MAX_AGENT_COUNT &&
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
  pendingMicSend.value = null
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
/** True while replaying via avatar speak (word lipsync). */
const manualReplayUsesAvatar = ref(false)

function stillOwnsManualReplay(abort: AbortController): boolean {
  return manualReplayAbortController === abort
}

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
  manualReplayUsesAvatar.value = false
}

async function playTurnAudioManual(turn: Turn, key: string) {
  if (!turn.audio_url) return

  // Resume only applies to paused plain-audio replay.
  if (
    manualReplayTurnKey.value === key &&
    manualReplayPaused.value &&
    currentAudio.value &&
    !manualReplayUsesAvatar.value
  ) {
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

  const useAvatar =
    isAgentTurn(turn) &&
    avatarsEnabled.value &&
    avatarWarmedUp.value &&
    isLipSyncPayload(turn.lipsync)

  if (useAvatar) {
    manualReplayUsesAvatar.value = true
    const played = await playAgentTurnAudio(turn)
    // Superseded by another replay/stop — do not touch shared flags.
    if (!stillOwnsManualReplay(abort)) return
    // Avatar "pause" stops speak; keep turn key so Replay can restart.
    if (manualReplayPaused.value) return
    if (abort.signal.aborted) {
      manualReplayActive.value = false
      manualReplayUsesAvatar.value = false
      manualReplayAbortController = null
      return
    }
    if (!played) {
      manualReplayUsesAvatar.value = false
      await playPlainAudioAndWait(turn.audio_url, abort.signal)
    }
  } else {
    manualReplayUsesAvatar.value = false
    await playPlainAudioAndWait(turn.audio_url, abort.signal)
  }

  if (!stillOwnsManualReplay(abort)) return

  manualReplayAbortController = null
  manualReplayUsesAvatar.value = false

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

function lastAudioTurnForAgent(agentId: string): Turn | undefined {
  return [...turns.value].reverse().find((t) => t.speaker === agentId && !!t.audio_url)
}

/** Agents whose last turn finished playing and can be replayed via the character menu. */
const replayableAgentIds = computed(() =>
  agentParticipants.value
    .filter((p) => {
      const turn = lastAudioTurnForAgent(p.id)
      return !!turn && completedAgentPlaybackKeys.value.includes(turnKey(turn))
    })
    .map((p) => p.id),
)

/** Agent whose turn is currently replaying via the character menu. */
const replayingAgentId = computed(() => {
  if (!manualReplayActive.value || manualReplayPaused.value || !manualReplayTurnKey.value) return null
  const turn = turns.value.find((t) => turnKey(t) === manualReplayTurnKey.value)
  return turn && isAgentTurn(turn) ? turn.speaker : null
})

function replayAgentLastTurn(agentId: string) {
  const turn = lastAudioTurnForAgent(agentId)
  if (!turn) return
  void playTurnAudioManual(turn, turnKey(turn))
}

/** The agent turn shown in the speech bubble (text + anchor derived together). */
const speakingBubbleTurn = computed(() => {
  if (!showSpeechBubble.value) return null
  const key =
    liveSpeakingTurnKey.value ??
    (manualReplayActive.value && !manualReplayPaused.value ? manualReplayTurnKey.value : null)
  if (!key) return null
  const turn = turns.value.find((t) => turnKey(t) === key)
  return turn && isAgentTurn(turn) ? turn : null
})

function handleEvent(e: ConversationWsEvent) {
  if (e.type === 'connected') {
    connected.value = true
  }
  if (e.type === 'session_started') {
    sessionId.value = e.session_id
    sessionMaxTurns.value = e.max_turns ?? 0
    sessionTurnCount.value = e.turn_count ?? 0
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
    wsSessionBound.value = true
    void router.replace({ name: 'conversation-session', params: { id: e.session_id } })
  }
  if (e.type === 'session_resumed') {
    const silent = pendingSilentResumeSessionId === e.session_id
    if (silent) {
      pendingSilentResumeSessionId = null
    }

    sessionId.value = e.session_id
    sessionMaxTurns.value = e.max_turns ?? 0
    sessionTurnCount.value = e.turn_count ?? 0
    topic.value = e.topic || topic.value
    isEnded.value = false
    isPaused.value = e.paused ?? false
    needUserTurn.value = e.need_user_turn ?? false
    agentStatus.value = 'idle'
    wsSessionBound.value = true

    if (e.rebind) {
      if (!e.need_user_turn) {
        needFirstTurnChoice.value = false
      }
    } else {
      needFirstTurnChoice.value = false
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
      if (Number(route.params.id) !== e.session_id) {
        void router.replace({ name: 'conversation-session', params: { id: e.session_id } })
      }
      if (!silent) {
        toast({
          title: 'Discussion resumed',
          description: 'Pick up where you left off.',
        })
      }
    }
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
      wsSessionBound.value = false
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
  if (e.type === 'user_turn_blocked') {
    toast({
      title: 'Discussion wrapping up',
      description: 'Agents are finishing the conversation; your turn is no longer available.',
    })
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
    if (pendingSilentResumeSessionId === null) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' })
    }
    // Empty utterance: keep the user's turn open so they can speak again.
    if (/empty utterance/i.test(e.message ?? '')) {
      needUserTurn.value = true
      micState.value = 'idle'
      clearRecordingPreview()
    }
    // Resume from the URL failed (missing/foreign/finished session): back to setup.
    if (route.name === 'conversation-session' && !sessionId.value) {
      void router.replace({ name: 'conversation' })
    }
  }
}

function cancelWsWaits() {
  wsWaitCancel?.()
  wsWaitCancel = null
  pendingSilentResumeSessionId = null
  sessionResumePromise = null
}

function waitForSessionResumed(targetSessionId: number): Promise<void> {
  return new Promise((resolve, reject) => {
    let settled = false

    const finish = (action: () => void) => {
      if (settled) return
      settled = true
      window.clearTimeout(timeout)
      offEvent()
      offConn()
      if (wsWaitCancel === cleanup) {
        wsWaitCancel = null
      }
      action()
    }

    const cleanup = () => {
      finish(() => {})
    }

    const timeout = window.setTimeout(() => {
      pendingSilentResumeSessionId = null
      finish(() => reject(new Error('Session resume timeout')))
    }, SESSION_RESUME_TIMEOUT_MS)

    const offEvent = ws.onEvent((event) => {
      if (event.type === 'session_resumed' && event.session_id === targetSessionId) {
        finish(() => resolve())
      } else if (event.type === 'error') {
        pendingSilentResumeSessionId = null
        finish(() => reject(new Error(event.message)))
      }
    })

    const offConn = ws.onConnectionChange((open) => {
      if (!open) {
        pendingSilentResumeSessionId = null
        finish(() => reject(new Error('WebSocket connection lost')))
      }
    })

    wsWaitCancel = cleanup
    pendingSilentResumeSessionId = targetSessionId

    try {
      ws.send({ type: 'resume_session', session_id: targetSessionId, rebind: true })
    } catch (err) {
      pendingSilentResumeSessionId = null
      finish(() => reject(err))
    }
  })
}

async function ensureSessionReady(): Promise<void> {
  await ws.ready()
  if (!sessionId.value || isEnded.value || wsSessionBound.value) return

  if (!sessionResumePromise) {
    wsReconnecting.value = true
    sessionResumePromise = waitForSessionResumed(sessionId.value)
      .then(() => {
        wsSessionBound.value = true
      })
      .finally(() => {
        wsReconnecting.value = false
        sessionResumePromise = null
      })
  }
  await sessionResumePromise
}

async function sendSessionMessage(payload: Record<string, unknown>): Promise<void> {
  await ensureSessionReady()
  ws.send(payload)
}

function sendOrToast(action: () => Promise<void>) {
  void (async () => {
    try {
      await action()
    } catch (err: any) {
      toast({
        title: 'Could not send message',
        description: err?.message ?? 'Connection lost. Please try again.',
        variant: 'destructive',
      })
    }
  })()
}

/** Best-effort landscape lock on touch devices. Needs fullscreen + Android;
 *  a no-op on iOS/desktop — the portrait overlay in the template covers those. */
function lockLandscape() {
  if (!window.matchMedia('(pointer: coarse)').matches) return
  const orientation = screen.orientation as ScreenOrientation & {
    lock?: (o: string) => Promise<void>
  }
  document.documentElement.requestFullscreen?.().then(
    () => orientation.lock?.('landscape').catch(() => {}),
    () => {},
  )
}

function unlockOrientation() {
  screen.orientation?.unlock?.()
  if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
}

function startSession() {
  if (!authStore.user?.profile_completed) return
  lockLandscape()
  warmupAvatars()
  void (async () => {
    try {
      await ws.ready()
      ws.send({
        type: 'start_session',
        topic: topic.value.trim(),
        character_ids: selectedCharacterIds.value,
      })
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
  lockLandscape()
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
  if (!userTurnsAllowed.value) return
  sendOrToast(() => sendSessionMessage({ type: 'raise_hand' }))
}

function pauseOrResume() {
  sendOrToast(() => sendSessionMessage({ type: isPaused.value ? 'resume' : 'pause' }))
}

const exitConfirmOpen = ref(false)
const notebookOpen = ref(false)

function onExitClick() {
  if (isEnded.value) {
    exitToSetup()
    return
  }
  if (!sessionId.value) return
  leaveSessionWithoutEnding()
  toast({
    title: 'Session not ended',
    description: 'Your discussion is still open — continue it anytime from History.',
  })
}

/** Leave the game without ending: cycle the WS so the server treats the
 *  session like a closed tab (interrupted, resumable from History). */
function leaveSessionWithoutEnding() {
  exitToSetup()
  ws.close()
  ws.connect()
}

function confirmEndSession() {
  exitConfirmOpen.value = false
  sendOrToast(() => sendSessionMessage({ type: 'end_session' }))
}

/** Leave the game phase and return to session setup. */
function exitToSetup() {
  unlockOrientation()
  stopAllAudioPlayback()
  resetAvatars()
  clearRecordingPreview()
  sessionId.value = null
  isEnded.value = false
  turns.value = []
  participants.value = []
  endedArgumentSummary.value = null
  needUserTurn.value = false
  needFirstTurnChoice.value = false
  agentStatus.value = 'idle'
  micState.value = 'idle'
  notebookOpen.value = false
  exitConfirmOpen.value = false
  wsSessionBound.value = false
  if (route.name === 'conversation-session') {
    void router.replace({ name: 'conversation' })
  }
}

const statusText = computed(() => {
  if (isEnded.value) return 'Ended'
  if (wsReconnecting.value) return 'Reconnecting…'
  if (sessionInProgress.value && !connected.value) return 'Connection lost — refresh if this persists'
  if (isPaused.value) return 'Paused'
  if (agentStatus.value === 'searching_online' || agentStatus.value === 'thinking') {
    return activeAgentName.value ? `${activeAgentName.value} is thinking…` : 'Partner is thinking…'
  }
  if (liveSpeakingTurnKey.value) {
    const turn = turns.value.find((t) => turnKey(t) === liveSpeakingTurnKey.value)
    if (turn && isAgentTurn(turn)) return `${turnSpeakerLabel(turn)} is speaking…`
  }
  if (needFirstTurnChoice.value) return 'Choose who speaks first'
  if (needUserTurn.value) return 'Your turn'
  return 'Listening…'
})

function sendTextTurn() {
  const text = inputText.value.trim()
  if (!text) return
  sendOrToast(async () => {
    await sendSessionMessage({ type: 'user_turn', utterance: text, source: 'text' })
    pushLocalUserTurn(text)
    inputText.value = ''
    needUserTurn.value = false
  })
}

function chooseFirstTurn(speakFirst: boolean) {
  sendOrToast(async () => {
    await sendSessionMessage({ type: 'first_turn_choice', speak_first: speakFirst })
    needFirstTurnChoice.value = false
    if (speakFirst) {
      needUserTurn.value = true
    } else {
      agentStatus.value = 'thinking'
    }
  })
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
      const elapsedMs =
        recordingStartedAt != null ? performance.now() - recordingStartedAt : 0
      recordingStartedAt = null
      const shouldAutoSend = autoSendRecordingAfterStop.value
      autoSendRecordingAfterStop.value = false

      if (elapsedMs < MIN_RECORDING_MS) {
        clearRecordingPreview()
        micState.value = 'idle'
        toast({
          title: 'Too short',
          description: 'You have to speak for at least 1 second.',
        })
        return
      }

      const blob = new Blob(recordedChunks.value, { type: 'audio/webm' })
      recordedBlob.value = blob
      recordedUrl.value = URL.createObjectURL(blob)
      if (shouldAutoSend) {
        void sendRecording()
      } else {
        micState.value = 'preview'
      }
    }
    recorder.start()
    mediaRecorder.value = recorder
    recordingStartedAt = performance.now()
    micState.value = 'recording'
  } catch (err: any) {
    recordingStartedAt = null
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
  if (!recordedBlob.value && !pendingMicSend.value) return
  micState.value = 'transcribing'

  let text: string
  let audioUrl: string | null = null

  if (pendingMicSend.value) {
    text = pendingMicSend.value.text
    audioUrl = pendingMicSend.value.audioUrl
  } else {
    const blob = recordedBlob.value!
    try {
      const sttText = (await ConversationService.speechToText(blob)).trim()
      if (!sttText) {
        clearRecordingPreview()
        micState.value = 'idle'
        toast({
          title: 'No speech detected',
          description: 'Please speak again.',
        })
        return
      }
      text = sttText

      const currentSessionId = sessionId.value ? String(sessionId.value) : null
      let upload: { audio_url: string } | null = null
      if (currentSessionId) {
        try {
          upload = await ConversationService.uploadUserAudio(currentSessionId, blob)
        } catch (err: unknown) {
          console.warn('User audio upload failed; sending turn without audio_url', err)
        }
      }
      audioUrl = upload?.audio_url ?? null
      pendingMicSend.value = { text, audioUrl }
    } catch (err: any) {
      micState.value = 'error'
      toast({
        title: 'Transcription failed',
        description: err?.message ?? 'Failed to transcribe audio',
        variant: 'destructive',
      })
      return
    }
  }

  try {
    await sendSessionMessage({
      type: 'user_turn',
      utterance: text,
      source: 'mic',
      audio_url: audioUrl,
    })
    pushLocalUserTurn(text)
    pendingMicSend.value = null
    needUserTurn.value = false
    clearRecordingPreview()
    micState.value = 'idle'
  } catch (err: any) {
    micState.value = 'preview'
    toast({
      title: 'Could not send message',
      description: err?.message ?? 'Connection lost. Tap Send again to retry.',
      variant: 'destructive',
    })
  }
}

function redoRecording() {
  clearRecordingPreview()
  micState.value = 'idle'
}

const micButtonEnabled = computed(() => {
  if (micState.value === 'recording') return true
  return (micState.value === 'idle' || micState.value === 'error') && canStartMic.value
})

function onMicClick() {
  if (micState.value === 'recording') {
    stopRecording()
    return
  }
  if (micButtonEnabled.value) void startRecording()
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
  if (!canStartMic.value || needFirstTurnChoice.value) return
  void startRecording()
}

function handleRecordShortcut(event: KeyboardEvent) {
  if (event.code !== 'Space') return
  if (event.repeat) return
  if (event.metaKey || event.ctrlKey || event.altKey) return
  const focused = document.activeElement as HTMLElement | null
  if (focused) {
    const tag = focused.tagName?.toUpperCase()
    // Only yield Space to real typing contexts; focused buttons must not steal it
    // (e.g. Replay after click would otherwise re-fire on Space).
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    if (focused.isContentEditable) return
  }
  event.preventDefault()
  // Capture-phase + stopPropagation so Space never reaches the focused button
  // (reka-ui's own keydown handler would otherwise re-fire it). Enter still
  // activates buttons for keyboard users.
  event.stopPropagation()
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
    if (open) {
      connected.value = true
    } else {
      connected.value = false
      wsSessionBound.value = false
    }
  })
  window.addEventListener('keydown', handleRecordShortcut, true)
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

  const routeSessionId = Number(route.params.id)
  if (Number.isFinite(routeSessionId) && routeSessionId > 0) {
    resumeSession(routeSessionId)
  }
})

// Browser Back from the game URL to the setup URL reuses this component
// instance, so leave the session explicitly (same as the Exit button).
watch(
  () => route.name,
  (name) => {
    if (name === 'conversation' && sessionId.value && !isEnded.value) {
      leaveSessionWithoutEnding()
    }
    if (name === 'conversation-session' && !sessionId.value) {
      const routeSessionId = Number(route.params.id)
      if (Number.isFinite(routeSessionId) && routeSessionId > 0) {
        resumeSession(routeSessionId)
      }
    }
  },
)

onUnmounted(() => {
  hideAppNav.value = false
  unlockOrientation()
  window.removeEventListener('keydown', handleRecordShortcut, true)
  window.removeEventListener('pointerdown', handleConversationInteraction)
  clearEndedSummaryPollTimer()
  cancelWsWaits()
  clearRecordingPreview()
  stopAllAudioPlayback()
  resetAvatars()
  connected.value = false
  wsSessionBound.value = false
  ws.close()
})
</script>

<template>
  <div v-if="!showConversationPanel" class="container mx-auto space-y-6 px-4 py-8">
    <Card class="relative mx-auto max-w-5xl overflow-hidden rounded-2xl border-border/80 shadow-sm">
      <SakuraCorner class="opacity-80" :size="96" />
      <CardHeader class="relative z-[2] space-y-1">
        <CardTitle class="text-2xl font-bold">Discussion Setup</CardTitle>
        <CardDescription>
          Choose a topic, set the scene, then pick classmates for your seminar.
        </CardDescription>
      </CardHeader>
      <CardContent class="relative z-[2] space-y-6">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <div class="flex items-center gap-2 text-sm font-medium">
              <FolderOpen class="h-4 w-4 text-tag-foreground" />
              Major category
            </div>
            <Select v-model="selectedCategory" :disabled="sessionInProgress || isGeneratingScenario">
              <SelectTrigger class="h-11 w-full rounded-xl">
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
            <div class="flex items-center gap-2 text-sm font-medium">
              <BookOpen class="h-4 w-4 text-tag-foreground" />
              Subtopic
            </div>
            <Select
              v-model="selectedSubtopic"
              :disabled="!selectedCategory || sessionInProgress || isGeneratingScenario"
            >
              <SelectTrigger class="h-11 w-full rounded-xl">
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
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-sm font-medium">Discussion scenario</div>
            <Button
              variant="default"
              size="sm"
              class="rounded-xl font-semibold"
              :disabled="!canGenerateScenario"
              @click="generateDiscussionScenario"
            >
              <SakuraMark :size="14" class="text-primary-foreground" />
              {{ isGeneratingScenario ? 'Generating…' : 'Generate prompt' }}
            </Button>
          </div>
          <p v-if="isGeneratingScenario" class="text-sm text-muted-foreground">
            Preparing your scenario…
          </p>
          <p v-else-if="topic.trim() && scenarioArticles.length" class="text-sm text-muted-foreground">
            Scenario ready—you can edit it below before you start.
          </p>
          <Textarea
            v-model="topic"
            placeholder="Enter what you would like to discuss…"
            class="min-h-[100px] rounded-2xl"
          />
        </div>

        <div class="space-y-3">
          <div class="text-sm font-medium">Discussion environment</div>
          <div class="grid gap-3 sm:grid-cols-3">
            <button
              v-for="scene in SCENE_OPTIONS"
              :key="scene.id"
              type="button"
              class="group relative overflow-hidden rounded-2xl border text-left transition-all"
              :class="
                sceneId === scene.id
                  ? 'border-primary ring-2 ring-primary/30'
                  : 'border-border hover:border-primary/40'
              "
              :disabled="sessionInProgress"
              @click="sceneId = scene.id"
            >
              <div
                class="h-24 bg-cover bg-center"
                :style="{ backgroundImage: `url(${scene.url})` }"
              />
              <div class="flex items-center justify-between gap-2 px-3 py-2">
                <span class="text-sm font-medium">{{ scene.label }}</span>
                <span
                  v-if="sceneId === scene.id"
                  class="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground"
                >
                  <Check class="h-3 w-3" />
                </span>
              </div>
            </button>
          </div>
        </div>

        <Card class="rounded-2xl border-border/80 bg-muted/20">
          <CardHeader class="pb-3">
            <CardTitle class="text-lg font-bold">Choose Classmates</CardTitle>
            <CardDescription>
              Classmates who join you in the discussion.
            </CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <PartnerSelectPanel
              v-model="selectedCharacterIds"
              :disabled="sessionInProgress"
            />
            <div v-if="!sessionInProgress" class="pt-1">
              <Button
                class="h-11 rounded-xl px-8 text-base font-semibold"
                :disabled="!canStart"
                @click="startSession"
              >
                Start discussion
                <SakuraMark :size="16" class="text-primary-foreground" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </CardContent>
    </Card>
  </div>

  <!-- Game phase: immersive fullscreen scene. z-[60] covers the NavBar (z-50);
       portaled popover/menu content gets z-[70] to stay above this overlay. -->
  <div v-else class="fixed inset-0 z-[60] overflow-hidden">
    <!-- Gradient stays visible while the scene image loads -->
    <div class="absolute inset-0 bg-gradient-to-b from-pink-200/80 via-sky-100 to-amber-50" />
    <div
      class="absolute inset-0 scale-110 bg-cover bg-center"
      :style="{
        backgroundImage: `url(${sceneUrl})`,
        filter: `blur(${sceneBlur}px)`,
      }"
    />

    <!-- Stage: partner characters side-by-side. bottom-0 so characters clip at the
         screen edge instead of floating above a background strip. -->
    <div class="absolute inset-x-0 bottom-0 top-16">
      <AgentAvatarGrid
        ref="avatarGridRef"
        game
        :avatar-scale="avatarScale"
        class="h-full"
        :participants="participants"
        :active-speaker-id="activeSpeakerId"
        :agent-status="agentStatus"
        :warmed-up="avatarWarmedUp && avatarsEnabled"
        :bubble-text="speakingBubbleTurn?.utterance ?? null"
        :bubble-agent-id="speakingBubbleTurn?.speaker ?? null"
        :replayable-agent-ids="replayableAgentIds"
        :replaying-agent-id="replayingAgentId"
        @replay="replayAgentLastTurn"
        @stop-replay="stopManualTurnAudio"
      />
    </div>

    <!-- Exit (top-left): leaves without ending; the session stays resumable -->
    <Button
      variant="secondary"
      size="icon"
      class="absolute left-4 top-4 h-11 w-11 rounded-xl border border-white/30 bg-white/85 text-foreground shadow-lg backdrop-blur hover:bg-white"
      aria-label="Exit without ending session"
      @click="onExitClick"
    >
      <LogOut class="h-5 w-5" />
    </Button>

    <!-- Stop: ends the session (with confirmation) -->
    <Button
      v-if="sessionInProgress"
      variant="secondary"
      size="icon"
      class="absolute left-[4.75rem] top-4 h-11 w-11 rounded-xl border border-white/30 bg-white/85 text-destructive shadow-lg backdrop-blur hover:bg-white"
      aria-label="End session"
      @click="exitConfirmOpen = true"
    >
      <Square class="h-5 w-5 fill-current" />
    </Button>

    <!-- Status pill (top-center) -->
    <div
      class="absolute left-1/2 top-4 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/40 bg-white/90 px-4 py-1.5 text-sm text-foreground shadow-md backdrop-blur"
    >
      <SakuraMark :size="14" />
      <span class="whitespace-nowrap font-medium">{{ statusText }}</span>
      <button
        v-if="sessionInProgress"
        type="button"
        class="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-semibold text-primary hover:bg-primary/25"
        @click="pauseOrResume"
      >
        {{ isPaused ? 'Resume' : 'Pause' }}
      </button>
    </div>

    <!-- Settings (top-right) -->
    <Popover>
      <PopoverTrigger as-child>
        <Button
          variant="secondary"
          size="icon"
          class="absolute right-4 top-4 h-11 w-11 rounded-xl border border-white/30 bg-white/85 text-foreground shadow-lg backdrop-blur hover:bg-white"
          aria-label="Settings"
        >
          <Settings class="h-5 w-5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" class="z-[70] w-64 space-y-3">
        <div class="text-sm font-medium">Settings</div>
        <label class="flex items-center justify-between gap-3 text-sm">
          Show speech bubble
          <input v-model="showSpeechBubble" type="checkbox" class="h-4 w-4 accent-primary" />
        </label>
        <label class="flex items-center justify-between gap-3 text-sm">
          Character size
          <input
            v-model.number="avatarScale"
            type="range"
            min="0.5"
            max="2"
            step="0.05"
            class="w-28 accent-primary"
          />
        </label>
        <label class="flex items-center justify-between gap-3 text-sm">
          Show avatars
          <input
            type="checkbox"
            class="h-4 w-4 accent-primary"
            :checked="avatarsEnabled"
            @change="toggleAvatarsEnabled()"
          />
        </label>
        <div class="space-y-2">
          <div class="text-sm font-medium">Background</div>
          <label
            v-for="scene in SCENE_OPTIONS"
            :key="scene.id"
            class="flex items-center gap-2 text-sm"
          >
            <input
              v-model="sceneId"
              type="radio"
              class="h-4 w-4 accent-primary"
              :value="scene.id"
            />
            {{ scene.label }}
          </label>
          <label class="flex items-center justify-between gap-3 text-sm">
            Blur
            <input
              v-model.number="sceneBlur"
              type="range"
              min="0"
              max="20"
              step="1"
              class="w-28 accent-primary"
            />
          </label>
        </div>
      </PopoverContent>
    </Popover>

    <!-- Who speaks first? -->
    <div
      v-if="needFirstTurnChoice && !isEnded"
      class="pointer-events-none absolute inset-0 z-10 grid place-items-center p-4"
    >
      <Card class="pointer-events-auto w-[min(24rem,100%)] rounded-2xl shadow-xl">
        <CardHeader>
          <CardTitle class="text-base font-bold">Who speaks first?</CardTitle>
          <CardDescription>
            Decide whether you open the discussion or let one of your partners begin.
          </CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-2 sm:flex-row">
          <Button class="rounded-xl" :disabled="wsReconnecting" @click="chooseFirstTurn(true)">I’ll speak first</Button>
          <Button variant="outline" class="rounded-xl" :disabled="wsReconnecting" @click="chooseFirstTurn(false)">
            Let a partner start
          </Button>
        </CardContent>
      </Card>
    </div>

    <!-- Mic cluster (bottom-center) -->
    <div
      v-if="!isEnded"
      class="absolute bottom-6 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-2"
    >
      <div
        v-if="micState === 'preview' && recordedUrl"
        class="w-[min(20rem,calc(100vw-2rem))] space-y-2 rounded-2xl border border-border/80 bg-card p-3 shadow-xl"
      >
        <div class="text-sm font-medium">Preview recording</div>
        <audio :src="recordedUrl" controls class="w-full" />
        <div class="flex gap-2">
          <Button size="sm" class="rounded-xl" :disabled="!canStartMic || wsReconnecting" @click="sendRecording">Send</Button>
          <Button size="sm" variant="outline" class="rounded-xl" @click="redoRecording">Redo</Button>
        </div>
      </div>
      <button
        type="button"
        class="flex h-20 w-20 items-center justify-center rounded-full text-white shadow-xl transition-colors"
        :class="
          micState === 'recording'
            ? 'animate-pulse bg-red-500 ring-4 ring-red-300/70'
            : micButtonEnabled
              ? 'animate-pulse bg-primary ring-4 ring-primary/40 shadow-[0_0_28px_hsl(var(--primary)/0.55)] hover:bg-primary/90'
              : 'cursor-not-allowed bg-muted-foreground/40'
        "
        :disabled="!micButtonEnabled"
        aria-label="Speak"
        @click="onMicClick"
      >
        <Square v-if="micState === 'recording'" class="h-7 w-7" />
        <Loader2
          v-else-if="micState === 'transcribing' || micState === 'requesting'"
          class="h-7 w-7 animate-spin"
        />
        <Mic v-else class="h-8 w-8" />
      </button>
      <div
        v-if="micButtonEnabled"
        class="rounded-full bg-white/90 px-3 py-1 text-xs font-semibold text-foreground shadow backdrop-blur"
      >
        {{ micState === 'recording' ? 'Recording… press Space to stop' : 'Press Space to speak' }}
      </div>
    </div>

    <!-- Notebook: speaker opinions (bottom-right) -->
    <Button
      variant="secondary"
      size="icon"
      class="absolute bottom-6 right-4 z-10 h-11 w-11 rounded-xl border border-white/30 bg-white/85 text-foreground shadow-lg backdrop-blur hover:bg-white"
      aria-label="Speaker opinions"
      @click="notebookOpen = !notebookOpen"
    >
      <NotebookPen class="h-5 w-5" />
    </Button>
    <ArgumentSummaryPanel
      class="!bottom-20"
      :session-id="sessionId"
      :settled-turn-count="effectiveSettledTurnCount"
      :playback-busy="agentPlaybackBusy"
      :session-ended="isEnded"
      :visible="notebookOpen && showArgumentSummary"
      @summary-updated="onArgumentSummaryUpdated"
    />

    <!-- Results overlay -->
    <div v-if="isEnded" class="absolute inset-0 z-20 overflow-y-auto bg-background/95 p-6">
      <Card class="mx-auto max-w-3xl rounded-2xl border-border/80 shadow-lg">
        <CardHeader>
          <CardTitle class="text-2xl font-bold">Session complete</CardTitle>
          <CardDescription>Review the discussion and download your results.</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div v-if="turns.length > 0" class="space-y-2">
            <div class="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" class="rounded-xl" @click="downloadTranscript">
                Download transcript
              </Button>
              <Button
                variant="outline"
                size="sm"
                class="rounded-xl"
                :disabled="!canDownloadArgumentStructure"
                @click="downloadArgumentStructure"
              >
                Download speaker opinions
              </Button>
              <Button
                variant="outline"
                size="sm"
                class="rounded-xl"
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
          <div
            v-if="turns.length > 0"
            class="max-h-[50vh] space-y-4 overflow-y-auto rounded-2xl border border-border/80 bg-muted/20 p-4"
          >
            <div v-for="(turn, index) in turns" :key="turnKey(turn)" class="space-y-1">
              <div class="text-xs text-muted-foreground">
                Turn {{ index + 1 }} ·
                <span class="font-medium text-foreground">{{ turnSpeakerLabel(turn) }}</span>
              </div>
              <div class="whitespace-pre-wrap text-sm">{{ turn.utterance }}</div>
            </div>
          </div>
          <div v-else class="text-sm text-muted-foreground">No turns were recorded.</div>
          <Button class="rounded-xl font-semibold" @click="exitToSetup">Done</Button>
        </CardContent>
      </Card>
    </div>

    <!-- Exit confirmation (in-overlay: portaled dialogs z-fight with this fullscreen layer) -->
    <div
      v-if="exitConfirmOpen"
      class="absolute inset-0 z-30 grid place-items-center bg-black/60 p-4"
      @click.self="exitConfirmOpen = false"
    >
      <Card class="w-[min(26rem,100%)] shadow-xl bg-white/80">
        <CardHeader>
          <CardTitle class="text-base">End this session?</CardTitle>
          <CardDescription>
            The discussion will end, and you can download the transcript and speaker opinions.
          </CardDescription>
        </CardHeader>
        <CardContent class="flex justify-end gap-2">
          <Button variant="outline" @click="exitConfirmOpen = false">Cancel</Button>
          <Button variant="destructive" @click="confirmEndSession">End session</Button>
        </CardContent>
      </Card>
    </div>

    <!-- Portrait block: the stage is landscape-only on touch devices. Pure CSS so it
         tracks rotation with no JS; state stays mounted underneath. -->
    <div
      class="absolute inset-0 z-40 hidden flex-col items-center justify-center gap-4 bg-black/90 text-white [@media(orientation:portrait)_and_(pointer:coarse)]:flex"
    >
      <Smartphone class="h-12 w-12 rotate-90" />
      <p class="text-lg font-medium">Please rotate your device</p>
      <p class="text-sm text-white/70">This scene is designed for landscape</p>
    </div>
  </div>
</template>
