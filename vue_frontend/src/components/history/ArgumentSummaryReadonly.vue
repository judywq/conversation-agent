<script setup lang="ts">
import type {
  ArgumentSummaryEvidence,
  ArgumentSummaryResult,
  ArgumentSummarySpeaker,
} from '@/services/conversationService'

const props = defineProps<{
  summary: ArgumentSummaryResult | null | undefined
}>()

const EVIDENCE_LABELS: Record<string, string> = {
  fact: 'Fact',
  data: 'Data',
  example: 'Example',
}

function evidenceLabel(type: string): string {
  return EVIDENCE_LABELS[type] || 'Fact'
}

function evidenceLine(item: ArgumentSummaryEvidence): string {
  const label = evidenceLabel(item.type)
  const text = (item.text || '').trim()
  const turnPrefix = item.turn ? `Turn ${item.turn} · ` : ''
  return `${turnPrefix}${label}: ${text}`
}

function speakers(summary: ArgumentSummaryResult | null | undefined): ArgumentSummarySpeaker[] {
  if (!summary) return []
  if (summary.speakers?.length) return summary.speakers
  return []
}
</script>

<template>
  <div v-if="!summary || summary.status === 'empty'" class="text-sm text-muted-foreground">
    No structured arguments yet.
  </div>
  <ul v-else class="list-none space-y-3 text-sm">
    <li
      v-for="(speaker, speakerIndex) in speakers(summary)"
      :key="`${speaker.speaker_id}-${speakerIndex}`"
      class="space-y-1"
    >
      <div class="font-medium">{{ speaker.speaker_name || speaker.speaker_id }}</div>
      <div class="text-muted-foreground">Stance: {{ speaker.claim }}</div>
      <ul class="max-h-40 space-y-0.5 overflow-y-auto pl-2">
        <li
          v-for="(item, evidenceIndex) in speaker.evidence"
          :key="`${speaker.speaker_id}-evidence-${evidenceIndex}`"
          class="truncate text-[12px] leading-snug text-muted-foreground"
          :title="evidenceLine(item as ArgumentSummaryEvidence)"
        >
          {{ evidenceLine(item as ArgumentSummaryEvidence) }}
        </li>
      </ul>
    </li>
    <li v-if="speakers(summary).length === 0" class="text-muted-foreground">
      No structured arguments yet.
    </li>
  </ul>
</template>
