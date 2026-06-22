import type { ArgumentSummaryResult } from '@/services/conversationService'
import type { ConversationTurn } from '@/services/conversationWs'

const PACKAGE_LABELS: Record<string, string> = {
  argument: 'For',
  counterargument: 'Against',
}

const EXPLANATION_LABELS: Record<string, string> = {
  fact: 'Fact',
  data: 'Data',
  example: 'Example',
}

export function buildExportFilename(
  sessionId: number,
  kind: 'transcript' | 'arguments' | 'combined',
): string {
  return `conversation-${sessionId}-${kind}.txt`
}

export function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function formatTranscriptText(
  topic: string,
  turns: ConversationTurn[],
  speakerLabel: (turn: ConversationTurn) => string,
): string {
  const lines: string[] = []
  const trimmedTopic = topic.trim()
  if (trimmedTopic) {
    lines.push(`Discussion topic: ${trimmedTopic}`)
    lines.push('')
  }
  turns.forEach((turn, index) => {
    lines.push(`Turn ${index + 1} · ${speakerLabel(turn)}`)
    lines.push((turn.utterance || '').trim())
    lines.push('')
  })
  return lines.join('\n').trimEnd()
}

export function formatArgumentSummaryText(summary: ArgumentSummaryResult): string {
  if (summary.status !== 'ready') {
    return ''
  }

  const lines: string[] = []

  for (const claim of summary.claims || []) {
    const claimText = (claim.text || '').trim()
    if (!claimText) continue
    lines.push(`- ${claimText}`)

    for (const pkg of claim.arguments || []) {
      const packageLabel = PACKAGE_LABELS[pkg.type] || 'For'
      const reasonText = (pkg.reason?.text || '').trim()
      if (reasonText) {
        lines.push(`  - ${packageLabel}: ${reasonText}`)
      }
      for (const explanation of pkg.explanations || []) {
        const explanationText = (explanation.text || '').trim()
        if (!explanationText) continue
        const typeLabel = EXPLANATION_LABELS[explanation.type] || 'Fact'
        lines.push(`    - ${typeLabel}: ${explanationText}`)
      }
    }
  }

  return lines.join('\n')
}

export function formatCombinedExportText(
  topic: string,
  turns: ConversationTurn[],
  speakerLabel: (turn: ConversationTurn) => string,
  summary: ArgumentSummaryResult,
): string {
  const transcript = formatTranscriptText(topic, turns, speakerLabel)
  const argumentsText = formatArgumentSummaryText(summary)
  const parts = ['=== Transcript ===', transcript]
  if (argumentsText) {
    parts.push('', '=== Argument structure ===', argumentsText)
  }
  return parts.join('\n')
}
