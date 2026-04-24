<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/toast/use-toast'
import { ConversationService } from '@/services/conversationService'
import { ConversationWsClient, type ConversationWsEvent } from '@/services/conversationWs'

const { toast } = useToast()

const ws = new ConversationWsClient()
const connected = ref(false)
const sessionId = ref<number | null>(null)
const topic = ref('')

type Turn = {
  speaker: string
  speaker_type: string
  utterance: string
  turn_index: number
  audio_url?: string | null
}

const turns = ref<Turn[]>([])
const agentStatus = ref<'idle' | 'thinking' | 'finished'>('idle')
const needUserTurn = ref(false)
const needFirstTurnChoice = ref(false)
const inputText = ref('')
const isPaused = ref(false)

const micState = ref<'idle' | 'requesting' | 'recording' | 'transcribing' | 'error'>('idle')
const mediaRecorder = ref<MediaRecorder | null>(null)
const recordedChunks = ref<Blob[]>([])

const canStart = computed(() => connected.value && !sessionId.value)

function handleEvent(e: ConversationWsEvent) {
  if (e.type === 'connected') {
    connected.value = true
  }
  if (e.type === 'session_started') {
    sessionId.value = e.session_id
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
    isPaused.value = false
    needUserTurn.value = false
    needFirstTurnChoice.value = false
    agentStatus.value = 'idle'
  }
  if (e.type === 'need_user_turn') {
    needUserTurn.value = true
    needFirstTurnChoice.value = false
  }
  if (e.type === 'agent_status') {
    agentStatus.value = e.status
  }
  if (e.type === 'turn') {
    turns.value.push(e.turn)
    if (e.turn.speaker_type === 'user') needUserTurn.value = false
    if (e.turn.audio_url) {
      const audio = new Audio(e.turn.audio_url)
      audio.play().catch(() => undefined)
    }
  }
  if (e.type === 'error') {
    toast({ title: 'Error', description: e.message, variant: 'destructive' })
  }
}

function startSession() {
  ws.send({ type: 'start_session', topic: topic.value })
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
  recordedChunks.value = []
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    recorder.ondataavailable = (evt) => {
      if (evt.data.size > 0) recordedChunks.value.push(evt.data)
    }
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      micState.value = 'transcribing'
      try {
        const blob = new Blob(recordedChunks.value, { type: 'audio/webm' })
        const text = await ConversationService.speechToText(blob)
        ws.send({ type: 'user_turn', utterance: text, source: 'mic' })
        needUserTurn.value = false
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

onMounted(() => {
  ws.connect()
  const off = ws.onEvent(handleEvent)
  onUnmounted(() => off())
})

onUnmounted(() => {
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
            <Button :disabled="!canStart" @click="startSession">Start</Button>
            <Button variant="outline" :disabled="!sessionId" @click="volunteer">Request to speak</Button>
            <Button
              variant="outline"
              :disabled="!sessionId"
              @click="pauseOrResume"
            >
              {{ isPaused ? 'Resume' : 'Pause' }}
            </Button>
            <Button
              variant="destructive"
              :disabled="!sessionId"
              @click="stopConversation"
            >
              Stop
            </Button>
          </div>
        </div>

        <div class="text-sm text-muted-foreground">
          Status:
          <span v-if="isPaused">Paused</span>
          <span v-if="agentStatus === 'thinking'">Agent thinking…</span>
          <span v-else-if="needFirstTurnChoice">Choose who speaks first</span>
          <span v-else-if="needUserTurn">Your turn</span>
          <span v-else>Idle</span>
        </div>

        <Card v-if="needFirstTurnChoice" class="border">
          <CardHeader>
            <CardTitle class="text-base">Who speaks first?</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col gap-2 sm:flex-row">
            <Button @click="chooseFirstTurn(true)">I’ll speak first</Button>
            <Button variant="outline" @click="chooseFirstTurn(false)">Let an agent start</Button>
          </CardContent>
        </Card>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Card class="border">
            <CardHeader>
              <CardTitle class="text-base">Speak (microphone)</CardTitle>
            </CardHeader>
            <CardContent class="space-y-3">
              <div class="text-sm text-muted-foreground">Mic state: {{ micState }}</div>
              <div class="flex gap-2">
                <Button
                  :disabled="
                    !needUserTurn || needFirstTurnChoice || micState === 'recording' || micState === 'transcribing'
                  "
                  @click="startRecording"
                >
                  Record
                </Button>
                <Button
                  variant="outline"
                  :disabled="micState !== 'recording'"
                  @click="stopRecording"
                >
                  Stop
                </Button>
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
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Turns</CardTitle>
      </CardHeader>
      <CardContent class="space-y-3">
        <div v-if="turns.length === 0" class="text-sm text-muted-foreground">No turns yet.</div>
        <div v-for="t in turns" :key="t.turn_index" class="border rounded-md p-3 space-y-1">
          <div class="text-xs text-muted-foreground">
            #{{ t.turn_index }} · {{ t.speaker_type }} · {{ t.speaker }}
          </div>
          <div class="whitespace-pre-wrap text-sm">{{ t.utterance }}</div>
          <div v-if="t.audio_url" class="pt-1">
            <Button variant="outline" size="sm" @click="new Audio(t.audio_url!).play().catch(() => undefined)">
              Play audio
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

