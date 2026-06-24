<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import ArgumentSummaryReadonly from '@/components/history/ArgumentSummaryReadonly.vue'
import {
  ConversationService,
  type ConversationSessionDetail,
  type ConversationSessionSummary,
} from '@/services/conversationService'
import type { ConversationTurn } from '@/services/conversationWs'
import {
  buildExportFilename,
  downloadTextFile,
  formatArgumentSummaryText,
  formatCombinedExportText,
  formatTranscriptText,
} from '@/lib/conversationExport'

const router = useRouter()

const sessions = ref<ConversationSessionSummary[]>([])
const loading = ref(false)
const errorMessage = ref('')
const expandedId = ref<number | null>(null)
const detailCache = ref<Record<number, ConversationSessionDetail>>({})
const detailLoadingId = ref<number | null>(null)

function formatSessionDate(value: string | null | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function sessionStatusLabel(session: ConversationSessionSummary): string {
  if (session.can_continue) return 'Interrupted'
  if (session.terminate || session.turn_count >= session.max_turns) return 'Ended'
  if (session.paused) return 'Paused'
  return 'In progress'
}

function continueSession(sessionId: number) {
  void router.push({ name: 'conversation', query: { resume: String(sessionId) } })
}

function displayTurnNumber(turns: ConversationTurn[], index: number): number {
  let number = 0
  let previousIndex: number | null = null
  for (let i = 0; i <= index; i += 1) {
    const turn = turns[i]
    if (turn.turn_index !== previousIndex) {
      number += 1
      previousIndex = turn.turn_index
    }
    if (i === index) return number
  }
  return index + 1
}

function speakerLabel(turn: ConversationTurn): string {
  if (turn.speaker_display_name) return turn.speaker_display_name
  if (turn.speaker_type === 'user') return 'You'
  return turn.speaker || 'Partner'
}

async function loadSessions() {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await ConversationService.fetchSessionHistory(50, 0)
    sessions.value = result.results
  } catch {
    errorMessage.value = 'Could not load discussion history.'
  } finally {
    loading.value = false
  }
}

async function toggleSession(sessionId: number) {
  if (expandedId.value === sessionId) {
    expandedId.value = null
    return
  }
  expandedId.value = sessionId
  if (detailCache.value[sessionId]) return

  detailLoadingId.value = sessionId
  try {
    detailCache.value[sessionId] = await ConversationService.fetchSessionDetail(sessionId)
  } catch {
    errorMessage.value = 'Could not load discussion details.'
    expandedId.value = null
  } finally {
    detailLoadingId.value = null
  }
}

function sessionDetail(sessionId: number): ConversationSessionDetail | null {
  return detailCache.value[sessionId] ?? null
}

function downloadTranscript(detail: ConversationSessionDetail) {
  const content = formatTranscriptText(detail.topic, detail.turns, speakerLabel)
  if (!content) return
  downloadTextFile(buildExportFilename(detail.id, 'transcript'), content)
}

function downloadArguments(detail: ConversationSessionDetail) {
  const content = formatArgumentSummaryText(detail.argument_summary)
  if (!content) return
  downloadTextFile(buildExportFilename(detail.id, 'arguments'), content)
}

function downloadCombined(detail: ConversationSessionDetail) {
  const content = formatCombinedExportText(
    detail.topic,
    detail.turns,
    speakerLabel,
    detail.argument_summary,
  )
  if (!content) return
  downloadTextFile(buildExportFilename(detail.id, 'combined'), content)
}

onMounted(() => {
  void loadSessions()
})
</script>

<template>
  <div v-if="loading" class="text-sm text-muted-foreground">Loading history…</div>
  <div v-else-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</div>
  <div v-else-if="sessions.length === 0" class="text-sm text-muted-foreground">
    No discussions yet. Start a conversation to build your history.
  </div>

  <div v-else class="space-y-3">
    <div v-for="session in sessions" :key="session.id" class="rounded-md border">
      <div class="flex items-center gap-2">
        <Button
          v-if="session.can_continue"
          size="sm"
          @click.stop="continueSession(session.id)"
        >
          Continue
        </Button>
        <button
          type="button"
          class="flex min-w-0 flex-1 items-center justify-between gap-3 px-4 py-3 text-left text-sm"
          @click="toggleSession(session.id)"
        >
          <div class="min-w-0 flex-1 space-y-1">
            <div class="font-medium truncate">{{ session.topic || 'Untitled discussion' }}</div>
            <div class="text-xs text-muted-foreground">
              {{ formatSessionDate(session.created_at) }}
              · {{ session.turn_count }} turns
              · {{ sessionStatusLabel(session) }}
            </div>
          </div>
          <ChevronDown
            class="h-4 w-4 shrink-0 text-muted-foreground transition-transform"
            :class="{ 'rotate-180': expandedId === session.id }"
          />
        </button>
      </div>

      <div v-if="expandedId === session.id" class="space-y-4 border-t px-4 py-4">
        <div v-if="detailLoadingId === session.id" class="text-sm text-muted-foreground">
          Loading details…
        </div>
        <template v-else-if="sessionDetail(session.id)">
          <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div class="space-y-2">
              <h3 class="text-sm font-medium">Transcript</h3>
              <div class="max-h-[min(60vh,28rem)] space-y-4 overflow-y-auto rounded-md border p-3">
                <div
                  v-for="(turn, index) in sessionDetail(session.id)!.turns"
                  :key="`${turn.turn_index}-${turn.subturn_index}-${index}`"
                  class="space-y-2 border-b pb-3 last:border-b-0 last:pb-0"
                >
                  <div class="text-xs text-muted-foreground">
                    Turn {{ displayTurnNumber(sessionDetail(session.id)!.turns, index) }} ·
                    <span class="font-medium text-foreground">{{ speakerLabel(turn) }}</span>
                  </div>
                  <div class="whitespace-pre-wrap text-sm">{{ turn.utterance }}</div>
                  <audio
                    v-if="turn.audio_url"
                    :src="turn.audio_url"
                    controls
                    preload="none"
                    class="h-8 w-full max-w-md"
                  />
                </div>
              </div>
            </div>

            <div class="space-y-2">
              <h3 class="text-sm font-medium">Argument structure</h3>
              <div class="max-h-[min(60vh,28rem)] overflow-y-auto rounded-md border p-3">
                <ArgumentSummaryReadonly :summary="sessionDetail(session.id)!.argument_summary" />
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <Button
              v-if="session.can_continue"
              size="sm"
              @click="continueSession(session.id)"
            >
              Continue discussion
            </Button>
            <Button variant="outline" size="sm" @click="downloadTranscript(sessionDetail(session.id)!)">
              Download transcript
            </Button>
            <Button
              variant="outline"
              size="sm"
              :disabled="sessionDetail(session.id)!.argument_summary.status !== 'ready'"
              @click="downloadArguments(sessionDetail(session.id)!)"
            >
              Download argument structure
            </Button>
            <Button
              variant="outline"
              size="sm"
              :disabled="sessionDetail(session.id)!.argument_summary.status !== 'ready'"
              @click="downloadCombined(sessionDetail(session.id)!)"
            >
              Download both
            </Button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
