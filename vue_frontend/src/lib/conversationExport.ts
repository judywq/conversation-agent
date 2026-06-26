import type { ArgumentSummaryResult } from '@/services/conversationService'
import type { ConversationTurn } from '@/services/conversationWs'
import { formatSpeakerOpinionsText } from '@/lib/argumentSummaryDisplay'

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
  return formatSpeakerOpinionsText(summary)
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
