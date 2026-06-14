declare module '@met4citizen/talkinghead/modules/lipsync-en.mjs' {
  export class LipsyncEn {}
}

declare module '@met4citizen/talkinghead' {
  export class TalkingHead {
    audioCtx: AudioContext
    lipsync: Record<string, unknown>
    constructor(node: HTMLElement, opt?: Record<string, unknown>)
    showAvatar(options: Record<string, unknown>): Promise<void>
    speakAudio(payload: Record<string, unknown>): void
  }
}
