<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AgentAvatarGrid from '@/components/conversation/AgentAvatarGrid.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
const turnList = computed<Turn[]>(() => turns.value)
const agentStatus = ref<'idle' | 'thinking' | 'finished' | 'searching_online'>('idle')
const activeAgentName = ref('')
const avatarsEnabled = ref(true)
const avatarWarmedUp = ref(false)
const avatarGridRef = ref<InstanceType<typeof AgentAvatarGrid> | null>(null)
const avatarSpeaking = ref(false)
const agentParticipants = computed(() => participants.value.filter((p) => p.type === 'agent'))
const activeSpeakerId = computed(() => {
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

type TurnAudioJob = { turn: Turn }

const turnAudioQueue = ref<TurnAudioJob[]>([])
const isProcessingTurnAudio = ref(false)
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
  if (isProcessingTurnAudio.value) return
  if (turnAudioQueue.value.length > 0) return
  if (currentAudio.value) return
  if (avatarSpeaking.value) return
  const finalize = pendingTermination.value
  pendingTermination.value = null
  finalize()
}

function stopPlainAudio() {
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value.currentTime = 0
    currentAudio.value = null
  }
}

function stopAllAudioPlayback() {
  playbackAbortController?.abort()
  playbackAbortController = null
  turnAudioQueue.value = []
  stopPlainAudio()
  avatarGridRef.value?.setIdleAll?.()
  avatarSpeaking.value = false
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

async function processTurnAudioQueue() {
  if (isProcessingTurnAudio.value) return
  isProcessingTurnAudio.value = true

  while (turnAudioQueue.value.length > 0) {
    const job = turnAudioQueue.value.shift()
    if (!job) break

    const abort = new AbortController()
    playbackAbortController = abort
    avatarSpeaking.value = true

    await playTurnAudioAndWait(job.turn, abort.signal)

    if (abort.signal.aborted) {
      break
    }
  }

  playbackAbortController = null
  avatarSpeaking.value = false
  isProcessingTurnAudio.value = false
  maybeFirePendingTermination()

  if (turnAudioQueue.value.length > 0) {
    void processTurnAudioQueue()
  }
}

function enqueueTurnAudio(turn: Turn) {
  if (!turn.audio_url) return
  turnAudioQueue.value.push({ turn })
  void processTurnAudioQueue()
}

function handleTurnAudio(turn: Turn) {
  enqueueTurnAudio(turn)
}

function playAudioNow(url: string) {
  if (!url) return
  const turn = [...turns.value].reverse().find((t) => t.audio_url === url)
  if (!turn?.audio_url) return
  stopAllAudioPlayback()
  enqueueTurnAudio(turn)
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
      resetAvatars()
    }

    if (e.type === 'session_ended') {
      // User-initiated end: stop audio now.
      flushAudio()
      applyEndedState()
    } else {
      // Natural max-turns termination: let the last audio finish before flipping UI state.
      if (
        isProcessingTurnAudio.value ||
        turnAudioQueue.value.length > 0 ||
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
    turns.value.push(e.turn)
    if (e.turn.speaker_type === 'user') needUserTurn.value = false
    void handleTurnAudio(e.turn)
  }
  if (e.type === 'error') {
    toast({ title: 'Error', description: e.message, variant: 'destructive' })
  }
}

function startSession() {
  if (!authStore.user?.profile_completed) return
  warmupAvatars()
  ws.send({ type: 'start_session', topic: topic.value.trim(), agent_count: agentCount.value })
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
      title: 'Could not load news topics',
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
    const description =
      result.knowledge_source === 'web'
        ? 'Scenario generated from subtopic; background fetched from web.'
        : `Generated from ${result.article_ids.length} article(s).`
    toast({
      title: 'Scenario ready',
      description,
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
  window.addEventListener('keydown', handleRecordShortcut)
  window.addEventListener('pointerdown', handleConversationInteraction, { once: false })
  onUnmounted(() => off())
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
  ws.close()
})
</script>

<template>
  <div class="container mx-auto py-8 px-4 space-y-6">
    <Card>
      <CardHeader>
        <CardTitle>Conversation</CardTitle>
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
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            :disabled="!canGenerateScenario"
            @click="generateDiscussionScenario"
          >
            {{ isGeneratingScenario ? 'Generating scenario…' : 'Generate scenario' }}
          </Button>
          <p v-if="isGeneratingScenario" class="text-sm text-muted-foreground">
            Fetching article content and generating scenario…
          </p>
          <p v-else-if="scenarioArticles.length" class="text-sm text-muted-foreground">
            Based on {{ scenarioArticles.length }} article{{ scenarioArticles.length === 1 ? '' : 's' }}:
            {{ scenarioArticles.map((article) => article.title).join(', ') }}
          </p>
        </div>

        <div class="space-y-2">
          <div class="text-sm font-medium">Discussion scenario</div>
          <Textarea v-model="topic" placeholder="Generate a scenario or enter your own topic…" class="min-h-[80px]" />
        </div>

        <div class="text-sm text-muted-foreground">
          Status:
          <span v-if="isEnded">Ended</span>
          <span v-else-if="isPaused">Paused</span>
          <span v-else-if="!authStore.user?.profile_completed">Complete your profile first</span>
          <span v-else-if="agentStatus === 'searching_online'">{{ activeAgentName || 'Agent' }} is checking online…</span>
          <span v-else-if="agentStatus === 'thinking'">{{ activeAgentName || 'Agent' }} is thinking…</span>
          <span v-else-if="needFirstTurnChoice">Choose who speaks first</span>
          <span v-else-if="needUserTurn">Your turn</span>
          <span v-else>Idle</span>
        </div>

        <Card class="border">
          <CardHeader>
            <CardTitle class="text-base">Agents</CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <div class="text-sm text-muted-foreground">
              Choose how many agent participants to include (1–{{ MAX_AGENT_COUNT }}).
            </div>
            <div class="flex items-center gap-3">
              <div class="text-sm font-medium w-28">Agent count</div>
              <select
                v-model.number="agentCount"
                class="h-9 rounded-md border bg-background px-3 text-sm"
                :disabled="!!sessionId"
              >
                <option v-for="n in MAX_AGENT_COUNT" :key="n" :value="n">{{ n }}</option>
              </select>
            </div>
          </CardContent>
        </Card>

        <Card v-if="needFirstTurnChoice" class="border">
          <CardHeader>
            <CardTitle class="text-base">Who speaks first?</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col gap-2 sm:flex-row">
            <Button @click="chooseFirstTurn(true)">I’ll speak first</Button>
            <Button variant="outline" @click="chooseFirstTurn(false)">Let an agent start</Button>
          </CardContent>
        </Card>

        <Card v-if="sessionId && participants.length > 0" class="border">
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
              <div class="text-xs text-muted-foreground">{{ p.type }}</div>
            </div>
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
            Click anywhere to load 3D avatars
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
                <div v-if="turnList.length === 0" class="text-sm text-muted-foreground">No turns yet.</div>
                <div
                  v-for="t in turnList"
                  :key="`${t.turn_index}.${t.subturn_index ?? 0}`"
                  class="border rounded-md p-3 space-y-1"
                >
                  <div class="text-xs text-muted-foreground">
                    #{{ t.turn_index }} ·
                    <span class="font-medium text-foreground">{{ t.speaker_display_name || t.speaker }}</span>
                  </div>
                  <div class="whitespace-pre-wrap text-sm">{{ t.utterance }}</div>
                  <div v-if="t.audio_url" class="pt-1">
                    <Button variant="outline" size="sm" @click="playAudioNow(t.audio_url!)">
                      Play audio
                    </Button>
                  </div>
                </div>
                <div
                  v-if="agentStatus === 'searching_online' || agentStatus === 'thinking'"
                  class="border border-dashed rounded-md p-3 space-y-1 opacity-70 italic"
                >
                  <div class="text-xs text-muted-foreground">
                    <span v-if="agentStatus === 'searching_online'">
                      {{ activeAgentName || 'Agent' }} is checking online…
                    </span>
                    <span v-else>
                      {{ activeAgentName || 'Agent' }} is thinking…
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
                    Press
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

              <Card class="border">
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

              <Card class="border">
                <CardHeader>
                  <CardTitle class="text-base">Turn</CardTitle>
                </CardHeader>
                <CardContent class="space-y-2">
                  <div
                    v-if="needUserTurn && !needFirstTurnChoice && !isPaused"
                    class="rounded-md border border-emerald-300 bg-emerald-50/50 px-3 py-2 text-sm"
                  >
                    <div class="font-medium">Your turn to speak</div>
                    <div class="text-muted-foreground">Use mic or text to respond.</div>
                  </div>
                  <div v-else class="text-sm text-muted-foreground">Waiting…</div>
                </CardContent>
              </Card>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t">
              <Button :disabled="!canStart" @click="startSession">Start</Button>
              <Button variant="outline" :disabled="!sessionId" @click="volunteer">Request to speak</Button>
              <Button variant="outline" :disabled="!sessionId" @click="pauseOrResume">
                {{ isPaused ? 'Resume' : 'Pause' }}
              </Button>
              <Button variant="destructive" :disabled="!sessionId" @click="stopConversation">
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
            <div v-if="turnList.length === 0" class="text-sm text-muted-foreground">No turns yet.</div>
            <div
              v-for="t in turnList"
              :key="`${t.turn_index}.${t.subturn_index ?? 0}`"
              class="border rounded-md p-3 space-y-1"
            >
              <div class="text-xs text-muted-foreground">
                #{{ t.turn_index }} ·
                <span class="font-medium text-foreground">{{ t.speaker_display_name || t.speaker }}</span>
              </div>
              <div class="whitespace-pre-wrap text-sm">{{ t.utterance }}</div>
              <div v-if="t.audio_url" class="pt-1">
                <Button variant="outline" size="sm" @click="playAudioNow(t.audio_url!)">
                  Play audio
                </Button>
              </div>
            </div>
            <div
              v-if="agentStatus === 'searching_online' || agentStatus === 'thinking'"
              class="border border-dashed rounded-md p-3 space-y-1 opacity-70 italic"
            >
              <div class="text-xs text-muted-foreground">
                <span v-if="agentStatus === 'searching_online'">
                  {{ activeAgentName || 'Agent' }} is checking online…
                </span>
                <span v-else>
                  {{ activeAgentName || 'Agent' }} is thinking…
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
                Press
                <kbd class="mx-0.5 rounded border bg-muted px-1.5 py-0.5 font-mono text-[0.7rem]">Space</kbd>
                to start recording, then press again to stop and send.
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

          <Card class="border">
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

          <Card class="border">
            <CardHeader>
              <CardTitle class="text-base">Turn</CardTitle>
            </CardHeader>
            <CardContent class="space-y-2">
              <div
                v-if="needUserTurn && !needFirstTurnChoice && !isPaused"
                class="rounded-md border border-emerald-300 bg-emerald-50/50 px-3 py-2 text-sm"
              >
                <div class="font-medium">Your turn to speak</div>
                <div class="text-muted-foreground">Use mic or text to respond.</div>
              </div>
              <div v-else class="text-sm text-muted-foreground">Waiting…</div>
            </CardContent>
          </Card>
        </div>

        <div class="flex flex-wrap gap-2 pt-2 border-t">
          <Button :disabled="!canStart" @click="startSession">Start</Button>
          <Button variant="outline" :disabled="!sessionId" @click="volunteer">Request to speak</Button>
          <Button variant="outline" :disabled="!sessionId" @click="pauseOrResume">
            {{ isPaused ? 'Resume' : 'Pause' }}
          </Button>
          <Button variant="destructive" :disabled="!sessionId" @click="stopConversation">
            Stop
          </Button>
        </div>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
