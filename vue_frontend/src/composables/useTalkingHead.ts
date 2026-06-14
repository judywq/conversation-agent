import { ref, shallowRef, type Ref } from 'vue'
import { TalkingHead } from '@met4citizen/talkinghead'
import { LipsyncEn } from '@met4citizen/talkinghead/modules/lipsync-en.mjs'
import type { AvatarBody } from '@/config/avatarPresets'
import type { LipSyncPayload } from '@/types/lipsync'

export type TalkingHeadStatus = 'idle' | 'loading' | 'ready' | 'speaking' | 'error'

const audioBufferCache = new Map<string, AudioBuffer>()

async function fetchAudioBuffer(audioUrl: string, audioCtx: AudioContext): Promise<AudioBuffer> {
  const cached = audioBufferCache.get(audioUrl)
  if (cached) return cached
  const response = await fetch(audioUrl, { mode: 'cors', credentials: 'omit' })
  if (!response.ok) {
    throw new Error(`Failed to fetch audio (${response.status})`)
  }
  const buffer = await response.arrayBuffer()
  const decoded = await audioCtx.decodeAudioData(buffer.slice(0))
  audioBufferCache.set(audioUrl, decoded)
  return decoded
}

export function useTalkingHead(stageRef: Ref<HTMLElement | null>) {
  const status = ref<TalkingHeadStatus>('idle')
  const errorMessage = ref('')
  const head = shallowRef<TalkingHead | null>(null)
  let initPromise: Promise<boolean> | null = null

  async function init(url: string, body: AvatarBody): Promise<boolean> {
    if (head.value) return true
    if (initPromise) return initPromise

    initPromise = (async () => {
      const stage = stageRef.value
      if (!stage) {
        return false
      }

      status.value = 'loading'
      errorMessage.value = ''

      try {
        const instance = new TalkingHead(stage, {
          lipsyncModules: [],
          mixerGainSpeech: 2.2,
          cameraView: 'upper',
          cameraDistance: 0.05,
          cameraY: 0.02,
          cameraRotateEnable: false,
          cameraZoomEnable: false,
          cameraPanEnable: false,
        })
        instance.lipsync.en = new LipsyncEn()

        await instance.showAvatar({
          url,
          body,
          lipsyncLang: 'en',
          avatarMood: 'neutral',
        })

        head.value = instance
        status.value = 'ready'
        return true
      } catch (error) {
        console.error('TalkingHead init failed:', error)
        head.value = null
        status.value = 'error'
        errorMessage.value = error instanceof Error ? error.message : 'Avatar unavailable'
        return false
      } finally {
        initPromise = null
      }
    })()

    return initPromise
  }

  async function speak(audioUrl: string, lipsync: LipSyncPayload): Promise<boolean> {
    const instance = head.value
    if (!instance) return false

    try {
      if (instance.audioCtx?.state === 'suspended') {
        await instance.audioCtx.resume()
      }

      const audioBuffer = await fetchAudioBuffer(audioUrl, instance.audioCtx)
      status.value = 'speaking'

      instance.speakAudio({
        audio: audioBuffer,
        words: lipsync.words,
        wtimes: lipsync.wtimes,
        wdurations: lipsync.wdurations,
      })

      return true
    } catch (error) {
      console.error('TalkingHead speak failed:', error)
      status.value = 'ready'
      return false
    }
  }

  function setIdle() {
    if (status.value === 'speaking') {
      status.value = head.value ? 'ready' : 'idle'
    }
  }

  function dispose() {
    initPromise = null
    head.value = null
    status.value = 'idle'
    errorMessage.value = ''
    const stage = stageRef.value
    if (stage) {
      stage.replaceChildren()
    }
  }

  return {
    status,
    errorMessage,
    head,
    init,
    speak,
    setIdle,
    dispose,
  }
}

export function clearAudioBufferCache() {
  audioBufferCache.clear()
}
