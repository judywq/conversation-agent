<script setup lang="ts">
import {
  explanationLabel,
  explanationLine,
  speakersFromSummary,
} from '@/lib/argumentSummaryDisplay'
import type { ArgumentSummaryResult } from '@/services/conversationService'

defineProps<{
  summary: ArgumentSummaryResult | null | undefined
}>()
</script>

<template>
  <div v-if="!summary || summary.status === 'empty'" class="text-sm text-muted-foreground">
    No speaker opinions yet.
  </div>
  <ul v-else class="list-none space-y-3 text-sm">
    <li
      v-for="(speaker, speakerIndex) in speakersFromSummary(summary)"
      :key="`${speaker.speaker_id}-${speakerIndex}`"
      class="space-y-2"
    >
      <div class="font-medium">{{ speaker.speaker_name || speaker.speaker_id }}</div>
      <div
        v-for="(claim, claimIndex) in speaker.claims"
        :key="`${speaker.speaker_id}-claim-${claimIndex}`"
        class="space-y-1 pl-2"
      >
        <div class="text-foreground">{{ claim.text }}</div>
        <ul
          v-for="(reason, reasonIndex) in claim.reasons || []"
          :key="`${speaker.speaker_id}-reason-${claimIndex}-${reasonIndex}`"
          class="space-y-0.5 pl-2"
        >
          <li class="text-[12px] leading-snug text-muted-foreground">
            {{ reason.text }}
          </li>
          <li
            v-for="(explanation, explanationIndex) in reason.explanations || []"
            :key="`${speaker.speaker_id}-exp-${claimIndex}-${reasonIndex}-${explanationIndex}`"
            class="truncate pl-2 text-[11px] leading-snug text-muted-foreground"
            :title="explanationLine(explanation)"
          >
            {{ explanationLabel(explanation.type) }}: {{ explanation.text }}
          </li>
        </ul>
      </div>
    </li>
    <li v-if="speakersFromSummary(summary).length === 0" class="text-muted-foreground">
      No speaker opinions yet.
    </li>
  </ul>
</template>
