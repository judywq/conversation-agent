import type {
  ArgumentSummaryClaim,
  ArgumentSummaryExplanation,
  ArgumentSummaryReason,
  ArgumentSummaryResult,
  ArgumentSummarySpeaker,
} from '@/services/conversationService'

const EXPLANATION_LABELS: Record<string, string> = {
  fact: 'Fact',
  data: 'Data',
  example: 'Example',
}

export function explanationLabel(type: string): string {
  return EXPLANATION_LABELS[type] || 'Fact'
}

export function explanationLine(item: ArgumentSummaryExplanation): string {
  const label = explanationLabel(item.type)
  const text = (item.text || '').trim()
  return `${label}: ${text}`
}

function flatSpeakerToClaims(speaker: ArgumentSummarySpeaker): ArgumentSummaryClaim[] {
  if (speaker.claims?.length) {
    return speaker.claims
  }
  const claimText = (speaker.claim || '').trim()
  if (!claimText) {
    return []
  }
  const reasons: ArgumentSummaryReason[] = []
  for (const item of speaker.evidence || []) {
    const text = (item.text || '').trim()
    if (!text) continue
    reasons.push({
      text,
      explanations: [{ type: item.type || 'fact', text }],
    })
  }
  return [{ text: claimText, reasons }]
}

export function speakersFromSummary(
  summary: ArgumentSummaryResult | null | undefined,
): Array<ArgumentSummarySpeaker & { claims: ArgumentSummaryClaim[] }> {
  if (!summary?.speakers?.length) return []
  return summary.speakers
    .map((speaker) => ({
      ...speaker,
      claims: flatSpeakerToClaims(speaker),
    }))
    .filter((speaker) => speaker.claims.length > 0)
}

export function formatSpeakerOpinionsText(summary: ArgumentSummaryResult): string {
  if (summary.status !== 'ready') {
    return ''
  }

  const lines: string[] = ['Speaker opinions', '']
  for (const speaker of speakersFromSummary(summary)) {
    const name = (speaker.speaker_name || speaker.speaker_id || 'Speaker').trim()
    lines.push(name)
    for (const claim of speaker.claims) {
      const claimText = (claim.text || '').trim()
      if (!claimText) continue
      lines.push(`  Claim: ${claimText}`)
      for (const reason of claim.reasons || []) {
        const reasonText = (reason.text || '').trim()
        if (!reasonText) continue
        lines.push(`    Reason: ${reasonText}`)
        for (const explanation of reason.explanations || []) {
          const explanationText = (explanation.text || '').trim()
          if (!explanationText) continue
          lines.push(`      ${explanationLine(explanation)}`)
        }
      }
    }
    lines.push('')
  }

  return lines.join('\n').trimEnd()
}
