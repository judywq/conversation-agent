import type { ArgumentSummaryResult } from '@/services/conversationService'
import type { ConversationTurn } from '@/services/conversationWs'

const EVIDENCE_LABELS: Record<string, string> = {
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
  const speakerList = summary.speakers || []

  for (const speaker of speakerList) {
    const name = (speaker.speaker_name || speaker.speaker_id || 'Speaker').trim()
    const claim = (speaker.claim || '').trim()
    if (!claim) continue
    lines.push(`${name}`)
    lines.push(`  Stance: ${claim}`)
    for (const evidence of speaker.evidence || []) {
      const evidenceText = (evidence.text || '').trim()
      if (!evidenceText) continue
      const typeLabel = EVIDENCE_LABELS[evidence.type] || 'Fact'
      lines.push(`  - ${typeLabel}: ${evidenceText}`)
    }
    lines.push('')
  }

  return lines.join('\n').trimEnd()
}

export function formatCombinedExportText(
  topic: string,
  turns: ConversationTurn[],
  speakerLabel: (turn: ConversationTurn) => string,
  summary: ArgumentSummaryResult,
): string {
  const transcript = formatTranscriptText(topic, turns, speakerLabel)
  const argumentsText = formatArgumentSummaryText(summary)
  const parts = [transcript, argumentsText].filter(Boolean)
  return parts.join('\n\n---\n\n')
}
