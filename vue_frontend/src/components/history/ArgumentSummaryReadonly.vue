<script setup lang="ts">
import type {
  ArgumentSummaryClaim,
  ArgumentSummaryPackage,
  ArgumentSummaryResult,
} from '@/services/conversationService'

defineProps<{
  summary: ArgumentSummaryResult | null | undefined
}>()

const PACKAGE_LABELS: Record<ArgumentSummaryPackage['type'], string> = {
  argument: 'For',
  counterargument: 'Against',
}

const EXPLANATION_LABELS: Record<string, string> = {
  fact: 'Fact',
  data: 'Data',
  example: 'Example',
}

function packageLabel(pkg: ArgumentSummaryPackage): string {
  return PACKAGE_LABELS[pkg.type] || 'For'
}

function explanationLabel(type: string): string {
  return EXPLANATION_LABELS[type] || 'Fact'
}
</script>

<template>
  <div v-if="!summary || summary.status === 'empty'" class="text-sm text-muted-foreground">
    No argument structure recorded.
  </div>
  <div v-else-if="summary.status === 'failed'" class="text-sm text-destructive">
    Argument structure could not be generated.
  </div>
  <div v-else-if="summary.status === 'pending'" class="text-sm text-muted-foreground">
    Argument structure was still being generated.
  </div>
  <ul v-else class="list-none space-y-2 text-xs">
    <li
      v-for="(claim, claimIndex) in (summary.claims as ArgumentSummaryClaim[] | undefined) || []"
      :key="`claim-${claimIndex}`"
      class="space-y-1"
    >
      <div class="font-medium leading-snug">• {{ claim.text }}</div>
      <div
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
      </div>
    </li>
    <li v-if="!summary.claims?.length" class="text-muted-foreground">
      No argument structure recorded.
    </li>
  </ul>
</template>
