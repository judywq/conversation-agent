<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AgentAvatarGrid from '@/components/conversation/AgentAvatarGrid.vue'
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

const { toast } = useToast()
const authStore = useAuthStore()

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

type TurnDisplayItem = {
  key: string
  turn: Turn | null
  number: number
  showTranscript: boolean
  isCurrent: boolean
  userTurnPrompt: boolean
  statusHint: string
}

const turnDisplayList = computed((): TurnDisplayItem[] => {
  const items: TurnDisplayItem[] = turns.value.map((turn, index) => {
    const key = turnKey(turn)
    return {
      key,
      turn,
      number: index + 1,
      showTranscript: turn.speaker_type === 'user',
      isCurrent: liveSpeakingTurnKey.value === key || manualReplayTurnKey.value === key,
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
    !!sessionId.value &&
    !userTurnActive &&
    !isProcessingTurnPlayback.value &&
    turnPlaybackQueue.value.length === 0 &&
    (agentStatus.value === 'thinking' || agentStatus.value === 'searching_online')

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

  return items
})

const hasCurrentTurnHighlight = computed(() => turnDisplayList.value.some((item) => item.isCurrent))

function turnItemClass(isCurrent: boolean): string {
  return isCurrent
    ? 'rounded-md border border-emerald-300 bg-emerald-50/50 px-3 py-2 space-y-1 text-sm'
    : 'border rounded-md p-3 space-y-1'
}

function currentTurnSpeakerLabel(item: TurnDisplayItem): string {
  if (item.userTurnPrompt) return 'You'
  if (item.isCurrent && item.statusHint) return activeAgentName.value || 'A partner'
  if (!item.turn) return ''
  return item.turn.speaker_display_name || item.turn.speaker
}

function canShowReplayControls(item: TurnDisplayItem): boolean {
  if (!item.turn?.audio_url) return false
  if (liveSpeakingTurnKey.value === item.key || manualReplayTurnKey.value === item.key) return false
  if (item.turn.speaker_type === 'agent') {
    return completedAgentPlaybackKeys.value.includes(item.key)
  }
  return true
}
const agentStatus = ref<'idle' | 'thinking' | 'finished' | 'searching_online'>('idle')
const activeAgentName = ref('')
const avatarsEnabled = ref(true)
const avatarWarmedUp = ref(false)
const avatarGridRef = ref<InstanceType<typeof AgentAvatarGrid> | null>(null)
const avatarSpeaking = ref(false)
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

const canStart = computed(() => connected.value && !sessionId.value && !!topic.value.trim() && !!authStore.user?.profile_completed)

const availableSubtopics = computed(() => {
  const category = taxonomy.value.find((item) => item.slug === selectedCategory.value)
  return category?.subtopics ?? []
})

const canGenerateScenario = computed(
  () => !!selectedCategory.value && !!selectedSubtopic.value && !isGeneratingScenario.value && !sessionId.value,
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

function canPauseTurnAudio(key: string): boolean {
  if (manualReplayTurnKey.value !== key || manualReplayPaused.value || !manualReplayActive.value) {
    return false
  }
  if (currentAudio.value && !currentAudio.value.paused) return true
  return avatarSpeaking.value
}

function pauseTurnAudioManual() {
  if (!manualReplayTurnKey.value || manualReplayPaused.value) return
  if (currentAudio.value && !currentAudio.value.paused) {
    currentAudio.value.pause()
    manualReplayPaused.value = true
    return
  }
  manualReplayAbortController?.abort()
  avatarGridRef.value?.setIdleAll?.()
  avatarSpeaking.value = false
  manualReplayPaused.value = true
  manualReplayActive.value = false
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
  avatarSpeaking.value = true

  await playTurnAudioAndWait(turn, abort.signal)

  avatarSpeaking.value = false
  manualReplayAbortController = null

  if (abort.signal.aborted || manualReplayPaused.value) {
    manualReplayActive.value = false
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
    stopAllAudioPlayback()
    resetAvatars()
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
      sessionId.value = null
    }
    const flushAudio = () => {
      stopAllAudioPlayback()
      flushTurnPlaybackQueueToDisplay()
      resetAvatars()
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
        pendingTermination.value = applyEndedState
      } else {
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

function volunteer() {
  ws.send({ type: 'raise_hand' })
}

function pauseOrResume() {
  ws.send({ type: isPaused.value ? 'resume' : 'pause' })
}

function stopConversation() {
  if (!sessionId.value) return
  const ok = window.confirm('Stop the conversation? This will end the session.')
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
            <Select v-model="selectedCategory" :disabled="!!sessionId || isGeneratingScenario">
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
              :disabled="!selectedCategory || !!sessionId || isGeneratingScenario"
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
                :disabled="!!sessionId"
              >
                <option v-for="n in MAX_AGENT_COUNT" :key="n" :value="n">{{ n }}</option>
              </select>
            </div>
            <p class="text-xs text-muted-foreground">
              Choose how many partners join you (1–{{ MAX_AGENT_COUNT }}). More partners means a larger group discussion.
            </p>
            <div v-if="!sessionId" class="pt-2">
              <Button :disabled="!canStart" @click="startSession">Start</Button>
            </div>
          </CardContent>
        </Card>

        <template v-if="sessionId">
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

        <Card v-if="needFirstTurnChoice" class="border">
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
            v-if="sessionId && agentParticipants.length > 0"
            variant="outline"
            size="sm"
            @click="toggleAvatarsEnabled"
          >
            {{ avatarsEnabled ? 'Avatars On' : 'Avatars Off' }}
          </Button>
          <span v-if="sessionId && avatarsEnabled && !avatarWarmedUp" class="text-xs text-muted-foreground">
            Click anywhere to show your partners
          </span>
        </div>

        <div
          v-if="sessionId && agentParticipants.length > 0"
          class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(280px,360px)_1fr]"
        >
          <AgentAvatarGrid
            ref="avatarGridRef"
            :participants="participants"
            :active-speaker-id="activeSpeakerId"
            :agent-status="agentStatus"
            :warmed-up="avatarWarmedUp && avatarsEnabled"
          />

          <div class="space-y-4">
            <Card class="border">
              <CardHeader>
                <CardTitle>Turns</CardTitle>
              </CardHeader>
              <CardContent class="space-y-3">
                <div
                  v-if="turnDisplayList.length === 0 && !hasCurrentTurnHighlight"
                  class="text-sm text-muted-foreground"
                >
                  No turns yet.
                </div>
                <div
                  v-for="item in turnDisplayList"
                  :key="item.key"
                  :class="turnItemClass(item.isCurrent)"
                >
                  <div class="text-xs text-muted-foreground">
                    Turn {{ item.number }} ·
                    <span class="font-medium text-foreground">{{ currentTurnSpeakerLabel(item) }}</span>
                  </div>
                  <template v-if="item.userTurnPrompt">
                    <div class="font-medium">Your turn to speak</div>
                    <div class="text-muted-foreground">
                      {{ authStore.isStaff ? 'Use mic or text to respond.' : 'Use the microphone to respond.' }}
                    </div>
                  </template>
                  <div v-else-if="item.statusHint" class="text-muted-foreground">{{ item.statusHint }}</div>
                  <div v-else-if="item.showTranscript && item.turn" class="whitespace-pre-wrap text-sm">
                    {{ item.turn.utterance }}
                  </div>
                  <div v-if="canShowReplayControls(item)" class="flex flex-wrap gap-2 pt-1">
                    <Button variant="outline" size="sm" @click="playTurnAudioManual(item.turn!, item.key)">
                      Replay
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="!canPauseTurnAudio(item.key)"
                      @click="pauseTurnAudioManual"
                    >
                      Pause
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div class="grid grid-cols-1 gap-3" :class="{ 'sm:grid-cols-2': authStore.isStaff }">
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

              <Card v-if="authStore.isStaff" class="border">
                <CardHeader>
                  <CardTitle class="text-base">Speak (text)</CardTitle>
                </CardHeader>
                <CardContent class="space-y-3">
                  <Textarea v-model="inputText" placeholder="Type your message…" class="min-h-[80px]" />
                  <Button :disabled="!needUserTurn || needFirstTurnChoice || !inputText.trim()" @click="sendTextTurn">
                    Send
                  </Button>
                </CardContent>
              </Card>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t">
              <Button variant="destructive" @click="stopConversation">
                Stop
              </Button>
            </div>
          </div>
        </div>

        <template v-else>
        <Card class="border">
          <CardHeader>
            <CardTitle>Turns</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3">
            <div
              v-if="turnDisplayList.length === 0 && !hasCurrentTurnHighlight"
              class="text-sm text-muted-foreground"
            >
              No turns yet.
            </div>
            <div
              v-for="item in turnDisplayList"
              :key="item.key"
              :class="turnItemClass(item.isCurrent)"
            >
              <div class="text-xs text-muted-foreground">
                Turn {{ item.number }} ·
                <span class="font-medium text-foreground">{{ currentTurnSpeakerLabel(item) }}</span>
              </div>
              <template v-if="item.userTurnPrompt">
                <div class="font-medium">Your turn to speak</div>
                <div class="text-muted-foreground">
                  {{ authStore.isStaff ? 'Use mic or text to respond.' : 'Use the microphone to respond.' }}
                </div>
              </template>
              <div v-else-if="item.statusHint" class="text-muted-foreground">{{ item.statusHint }}</div>
              <div v-else-if="item.showTranscript && item.turn" class="whitespace-pre-wrap text-sm">
                {{ item.turn.utterance }}
              </div>
              <div v-if="canShowReplayControls(item)" class="flex flex-wrap gap-2 pt-1">
                <Button variant="outline" size="sm" @click="playTurnAudioManual(item.turn!, item.key)">
                  Replay
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  :disabled="!canPauseTurnAudio(item.key)"
                  @click="pauseTurnAudioManual"
                >
                  Pause
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <div class="grid grid-cols-1 gap-3" :class="{ 'sm:grid-cols-2': authStore.isStaff }">
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

          <Card v-if="authStore.isStaff" class="border">
            <CardHeader>
              <CardTitle class="text-base">Speak (text)</CardTitle>
            </CardHeader>
            <CardContent class="space-y-3">
              <Textarea v-model="inputText" placeholder="Type your message…" class="min-h-[80px]" />
              <Button :disabled="!needUserTurn || needFirstTurnChoice || !inputText.trim()" @click="sendTextTurn">
                Send
              </Button>
            </CardContent>
          </Card>
        </div>

        <div class="flex flex-wrap gap-2 pt-2 border-t">
          <Button variant="destructive" @click="stopConversation">
            Stop
          </Button>
        </div>
        </template>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
