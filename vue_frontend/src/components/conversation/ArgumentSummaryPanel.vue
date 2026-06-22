<script setup lang="ts">
import { ChevronDown, Minus } from 'lucide-vue-next'
import { onUnmounted, ref, watch } from 'vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ConversationService,
  type ArgumentSummaryClaim,
  type ArgumentSummaryPackage,
  type ArgumentSummaryResult,
} from '@/services/conversationService'

const props = defineProps<{
  sessionId: number | null
  visible: boolean
  turnCount: number
  embedded?: boolean
}>()

const emit = defineEmits<{
  'summary-updated': [summary: ArgumentSummaryResult]
}>()

const summary = ref<ArgumentSummaryResult | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const minimized = ref(false)

const PACKAGE_LABELS: Record<ArgumentSummaryPackage['type'], string> = {
  argument: 'For',
  counterargument: 'Against',
}

const EXPLANATION_LABELS: Record<string, string> = {
  fact: 'Fact',
  data: 'Data',
  example: 'Example',
}

let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollAttempts = 0
const MAX_POLL_ATTEMPTS = 30

function clearPollTimer() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

async function loadSummary() {
  if (!props.sessionId || !props.visible) return

  loading.value = true
  errorMessage.value = ''

  try {
    const result = await ConversationService.fetchArgumentSummary(props.sessionId)
    summary.value = result
    emit('summary-updated', result)

    if (result.status === 'pending' && pollAttempts < MAX_POLL_ATTEMPTS) {
      pollAttempts += 1
      clearPollTimer()
      pollTimer = setTimeout(() => {
        void loadSummary()
      }, 2000)
      return
    }

    if (result.status === 'failed') {
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
  summary.value = null
  errorMessage.value = ''
  if (props.sessionId && props.visible) {
    void loadSummary()
  } else {
    loading.value = false
  }
}

function packageLabel(pkg: ArgumentSummaryPackage): string {
  return PACKAGE_LABELS[pkg.type] || 'For'
}

function explanationLabel(type: string): string {
  return EXPLANATION_LABELS[type] || 'Fact'
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
  () => props.turnCount,
  (count, previous) => {
    if (!props.visible || !props.sessionId) return
    if (previous !== undefined && count > previous) {
      pollAttempts = 0
      void loadSummary()
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
        ? 'flex min-h-0 flex-col overflow-hidden rounded-lg border bg-background'
        : 'pointer-events-auto fixed bottom-4 left-4 right-4 z-40 sm:left-auto sm:right-4 sm:w-[min(22rem,calc(100vw-2rem))]'
    "
  >
    <div
      :class="
        embedded
          ? 'flex min-h-0 flex-1 flex-col overflow-hidden'
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
          Key points so far
        </p>

        <ScrollArea
          :class="
            embedded
              ? 'min-h-0 flex-1 max-h-[min(70vh,32rem)] lg:max-h-[min(70vh,28rem)]'
              : 'max-h-[min(50vh,28rem)]'
          "
        >
          <div class="space-y-2 px-3 py-2 text-xs">
            <div v-if="loading" class="text-muted-foreground">Building summary…</div>
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
              <ul
                v-for="(claim, claimIndex) in (summary.claims as ArgumentSummaryClaim[] | undefined) || []"
                :key="`claim-${claimIndex}`"
                class="list-none space-y-1.5"
              >
                <li class="font-medium leading-snug">• {{ claim.text }}</li>
                <li
                  v-for="(pkg, pkgIndex) in claim.arguments"
                  :key="`pkg-${claimIndex}-${pkgIndex}`"
                  class="pl-3"
                >
                  <div class="text-muted-foreground">{{ packageLabel(pkg) }}</div>
                  <ul class="mt-0.5 list-none space-y-0.5 pl-2">
                    <li class="leading-snug">• {{ pkg.reason.text }}</li>
                    <li
                      v-for="(explanation, expIndex) in pkg.explanations"
                      :key="`exp-${claimIndex}-${pkgIndex}-${expIndex}`"
                      class="pl-3 text-[11px] text-muted-foreground leading-snug"
                    >
                      {{ explanationLabel(explanation.type) }}: {{ explanation.text }}
                    </li>
                  </ul>
                </li>
              </ul>
              <div
                v-if="!summary.claims?.length && summary.status === 'ready'"
                class="text-muted-foreground"
              >
                No structured arguments yet.
              </div>
            </template>
          </div>
        </ScrollArea>
      </template>
    </div>
  </div>
</template>
