export type ConversationWsEvent =
  | { type: 'connected'; user_id: number }
  | { type: 'session_started'; session_id: number; topic: string }
  | { type: 'participants'; participants: Array<{ id: string; name: string; type: 'user' | 'agent'; persona_name?: string }> }
  | { type: 'need_first_turn_choice' }
  | { type: 'paused' }
  | { type: 'resumed' }
  | { type: 'session_ended' }
  | { type: 'need_user_turn'; reason: string }
  | { type: 'turn'; turn: any }
  | { type: 'agent_status'; status: 'thinking' | 'finished' | 'searching_online'; agent_display_name?: string }
  | { type: 'terminated'; reason: string }
  | { type: 'error'; message: string }
  | { type: string; [k: string]: any }

function toWsUrl(apiBaseUrl: string, path: string): string {
  const url = new URL(apiBaseUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  // apiBaseUrl points to /api, so keep host and use provided path
  url.pathname = path
  url.search = ''
  url.hash = ''
  return url.toString()
}

export class ConversationWsClient {
  private ws: WebSocket | null = null
  private listeners: Array<(e: ConversationWsEvent) => void> = []

  connect(): void {
    const apiBase = import.meta.env.VITE_API_BASE_URL as string
    const wsUrl = toWsUrl(apiBase, '/ws/conversation/')
    this.ws = new WebSocket(wsUrl)
    this.ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        this.listeners.forEach((l) => l(data))
      } catch {
        // ignore
      }
    }
  }

  onEvent(listener: (e: ConversationWsEvent) => void): () => void {
    this.listeners.push(listener)
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener)
    }
  }

  send(payload: any): void {
    this.ws?.send(JSON.stringify(payload))
  }

  close(): void {
    this.ws?.close()
    this.ws = null
  }
}

