<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/toast/use-toast'
import { AuthService } from '@/services/authService'
import { ConversationService, type CefrSample } from '@/services/conversationService'
import { ConversationWsClient, type ConversationWsEvent } from '@/services/conversationWs'
import { useAuthStore } from '@/stores/auth'

const { toast } = useToast()
const authStore = useAuthStore()

const ws = new ConversationWsClient()
const connected = ref(false)
const sessionId = ref<number | null>(null)
const topic = ref('')
const cefrSamples = ref<CefrSample[]>([])
const cefrSampleList = computed<CefrSample[]>(() => cefrSamples.value)
const selectedCefrLevel = ref<string | null>(null)
const isGeneratingCefr = ref(false)
const agentCount = ref<number>(3)

type Participant = {
  id: string
  name: string
  type: 'user' | 'agent'
  persona_name?: string
}

const participants = ref<Participant[]>([])

type Turn = {
  speaker: string
  speaker_display_name?: string
  speaker_type: string
  utterance: string
  turn_index: number
  subturn_index?: number
  audio_url?: string | null
}

const turns = ref<Turn[]>([])
const turnList = computed<Turn[]>(() => turns.value)
const agentStatus = ref<'idle' | 'thinking' | 'finished'>('idle')
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
const currentAudio = ref<HTMLAudioElement | null>(null)
const audioQueue = ref<string[]>([])

const canStart = computed(() => connected.value && !sessionId.value && !!topic.value.trim() && !!selectedCefrLevel.value)

watch(topic, () => {
  cefrSamples.value = []
  selectedCefrLevel.value = null
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

function playQueuedAudio() {
  if (currentAudio.value || audioQueue.value.length === 0) return
  const nextUrl = audioQueue.value.shift()
  if (!nextUrl) return
  const audio = new Audio(nextUrl)
  currentAudio.value = audio
  audio.onended = () => {
    currentAudio.value = null
    playQueuedAudio()
  }
  audio.onerror = () => {
    currentAudio.value = null
    playQueuedAudio()
  }
  audio.play().catch(() => {
    currentAudio.value = null
    playQueuedAudio()
  })
}

function enqueueAudio(url: string) {
  if (!url) return
  audioQueue.value.push(url)
  playQueuedAudio()
}

function playAudioNow(url: string) {
  if (!url) return
  audioQueue.value = []
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value.currentTime = 0
    currentAudio.value = null
  }
  audioQueue.value.push(url)
  playQueuedAudio()
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
    audioQueue.value = []
    if (currentAudio.value) {
      currentAudio.value.pause()
      currentAudio.value.currentTime = 0
      currentAudio.value = null
    }
  }
  if (e.type === 'participants') {
    participants.value = e.participants ?? []
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
    // Preserve logs on termination/end; only reset the live session controls.
    isEnded.value = true
    isPaused.value = false
    needUserTurn.value = false
    needFirstTurnChoice.value = false
    agentStatus.value = 'idle'
    sessionId.value = null
    audioQueue.value = []
    if (currentAudio.value) {
      currentAudio.value.pause()
      currentAudio.value.currentTime = 0
      currentAudio.value = null
    }
  }
  if (e.type === 'need_user_turn') {
    isEnded.value = false
    needUserTurn.value = true
    needFirstTurnChoice.value = false
  }
  if (e.type === 'agent_status') {
    agentStatus.value = e.status
  }
  if (e.type === 'turn') {
    isEnded.value = false
    turns.value.push(e.turn)
    if (e.turn.speaker_type === 'user') needUserTurn.value = false
    if (e.turn.audio_url) {
      enqueueAudio(e.turn.audio_url)
    }
  }
  if (e.type === 'error') {
    toast({ title: 'Error', description: e.message, variant: 'destructive' })
  }
}

function startSession() {
  if (!selectedCefrLevel.value) return
  AuthService.updateUser({
    cefr_level: selectedCefrLevel.value,
    cefr_sample_topic: topic.value.trim(),
  })
    .then((user) => {
      authStore.user = user
      authStore.saveState()
      ws.send({ type: 'start_session', topic: topic.value.trim(), agent_count: agentCount.value })
    })
    .catch((err: any) => {
      toast({
        title: 'Unable to start',
        description: err?.message ?? 'Please confirm a CEFR listening level first.',
        variant: 'destructive',
      })
    })
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
  if (speakFirst) needUserTurn.value = true
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
      micState.value = 'preview'
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

async function generateCefrSamples() {
  const trimmedTopic = topic.value.trim()
  if (!trimmedTopic) return
  isGeneratingCefr.value = true
  selectedCefrLevel.value = null
  try {
    const result = await ConversationService.generateCefrSamples(trimmedTopic)
    cefrSamples.value = result.samples
    toast({
      title: 'CEFR samples ready',
      description: 'Listen to the samples and choose the level you are comfortable with.',
    })
  } catch (err: any) {
    toast({
      title: 'Sample generation failed',
      description: err?.message ?? 'Could not generate CEFR listening samples.',
      variant: 'destructive',
    })
  } finally {
    isGeneratingCefr.value = false
  }
}

onMounted(() => {
  ws.connect()
  const off = ws.onEvent(handleEvent)
  onUnmounted(() => off())
})

onUnmounted(() => {
  clearRecordingPreview()
  audioQueue.value = []
  if (currentAudio.value) {
    currentAudio.value.pause()
    currentAudio.value.currentTime = 0
    currentAudio.value = null
  }
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
        <div class="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div class="flex-1 space-y-2">
            <div class="text-sm font-medium">Topic</div>
            <Textarea v-model="topic" placeholder="Enter a discussion topic…" class="min-h-[80px]" />
          </div>
          <div class="flex gap-2">
            <Button :disabled="!connected || !!sessionId || !topic.trim() || isGeneratingCefr || !authStore.user?.profile_completed" variant="outline" @click="generateCefrSamples">
              {{ isGeneratingCefr ? 'Generating...' : 'Generate CEFR samples' }}
            </Button>
          </div>
        </div>

        <div class="text-sm text-muted-foreground">
          Status:
          <span v-if="isEnded">Ended</span>
          <span v-else-if="isPaused">Paused</span>
          <span v-else-if="!authStore.user?.profile_completed">Complete your profile first</span>
          <span v-else-if="!selectedCefrLevel">Generate and choose a CEFR sample</span>
          <span v-else-if="agentStatus === 'thinking'">Agent thinking…</span>
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
              Choose how many agent participants to include (1–5).
            </div>
            <div class="flex items-center gap-3">
              <div class="text-sm font-medium w-28">Agent count</div>
              <select
                v-model.number="agentCount"
                class="h-9 rounded-md border bg-background px-3 text-sm"
                :disabled="!!sessionId"
              >
                <option v-for="n in 5" :key="n" :value="n">{{ n }}</option>
              </select>
            </div>
          </CardContent>
        </Card>

        <Card class="border">
          <CardHeader>
            <CardTitle class="text-base">Listen and choose your level</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3">
            <div class="text-sm text-muted-foreground">
              After entering a topic, generate six topic-based samples and choose the one you can comfortably follow.
            </div>
            <div v-if="cefrSampleList.length === 0" class="text-sm text-muted-foreground">
              No CEFR samples generated for this topic yet.
            </div>
            <div v-for="(sample, idx) in cefrSampleList" :key="sample.level" class="rounded-md border p-3">
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                  <div class="font-medium w-5 text-center">{{ idx + 1 }}</div>
                  <audio v-if="sample.audio_url" :src="sample.audio_url" controls class="h-8 max-w-[180px]" />
                </div>
                <Button
                  :variant="selectedCefrLevel === sample.level ? 'default' : 'outline'"
                  @click="selectedCefrLevel = sample.level"
                >
                  {{ selectedCefrLevel === sample.level ? 'Selected' : 'Choose' }}
                </Button>
              </div>
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
              </div>
              <div class="text-xs text-muted-foreground">{{ p.type }}</div>
            </div>
          </CardContent>
        </Card>

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
      </CardContent>
    </Card>
  </div>
</template>

