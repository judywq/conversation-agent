import type { LipSyncPayload } from '@/types/lipsync'

export type ConversationParticipant = {
  id: string
  name: string
  type: 'user' | 'agent'
  persona_name?: string
  gender?: string
  voice_title?: string
  avatar_body?: string
}

export type ConversationTurn = {
  speaker: string
  speaker_display_name?: string
  speaker_type: string
  utterance: string
  turn_index: number
  subturn_index?: number
  audio_url?: string | null
  lipsync?: LipSyncPayload | null
}

export type ConversationWsEvent =
  | { type: 'connected'; user_id: number }
  | { type: 'session_started'; session_id: number; topic: string }
  | {
      type: 'participants'
      participants: ConversationParticipant[]
    }
  | { type: 'need_first_turn_choice' }
  | { type: 'paused' }
  | { type: 'resumed' }
  | { type: 'session_ended' }
  | { type: 'need_user_turn'; reason: string }
  | { type: 'turn'; turn: ConversationTurn }
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
  private connectionListeners: Array<(open: boolean) => void> = []

  isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return
    }

    this.teardownSocket()

    const apiBase = import.meta.env.VITE_API_BASE_URL as string
    const wsUrl = toWsUrl(apiBase, '/ws/conversation/')
    const socket = new WebSocket(wsUrl)
    this.ws = socket

    socket.onopen = () => {
      this.notifyConnectionChange(true)
    }
    socket.onclose = () => {
      if (this.ws === socket) {
        this.ws = null
      }
      this.notifyConnectionChange(false)
    }
    socket.onerror = () => {
      // onclose follows
    }
    socket.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        this.listeners.forEach((l) => l(data))
      } catch {
        // ignore
      }
    }
  }

  ready(): Promise<void> {
    if (this.isOpen()) {
      return Promise.resolve()
    }

    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        offConn()
        reject(new Error('WebSocket connection timeout'))
      }, 10000)

      const offConn = this.onConnectionChange((open) => {
        if (open) {
          window.clearTimeout(timeout)
          offConn()
          resolve()
        }
      })

      this.connect()
    })
  }

  onEvent(listener: (e: ConversationWsEvent) => void): () => void {
    this.listeners.push(listener)
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener)
    }
  }

  onConnectionChange(listener: (open: boolean) => void): () => void {
    this.connectionListeners.push(listener)
    return () => {
      this.connectionListeners = this.connectionListeners.filter((l) => l !== listener)
    }
  }

  private notifyConnectionChange(open: boolean) {
    this.connectionListeners.forEach((listener) => listener(open))
  }

  send(payload: any): void {
    const socket = this.ws
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected')
    }
    socket.send(JSON.stringify(payload))
  }

  close(): void {
    this.teardownSocket()
    this.notifyConnectionChange(false)
  }

  private teardownSocket(): void {
    const socket = this.ws
    if (!socket) return

    this.ws = null
    socket.onopen = null
    socket.onclose = null
    socket.onmessage = null
    socket.onerror = null

    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close()
    }
  }
}
