declare module '@met4citizen/talkinghead' {
  export class TalkingHead {
    audioCtx: AudioContext
    constructor(node: HTMLElement, opt?: Record<string, unknown>)
    showAvatar(options: Record<string, unknown>): Promise<void>
    speakAudio(payload: Record<string, unknown>): void
  }
}
