import { ref, shallowRef, type Ref } from 'vue'
import { Application, extensions } from 'pixi.js'
import { Live2DModel, Live2DPlugin } from 'untitled-pixi-live2d-engine'

extensions.add(Live2DPlugin)

export type Live2DStatus = 'idle' | 'loading' | 'ready' | 'speaking' | 'error'

export type Live2DPresetInput = {
  url: string
  zoom?: number // extra zoom on top of fit-to-panel; default 2.4 (upper-body framing)
  anchorY?: number // vertical anchor 0..1 from model top; default 0.05
}

export function useLive2D(stageRef: Ref<HTMLElement | null>) {
  const status = ref<Live2DStatus>('idle')
  const errorMessage = ref('')
  const model = shallowRef<Live2DModel | null>(null)
  let app: Application | null = null
  let initPromise: Promise<boolean> | null = null
  let pendingSpeakResolve: ((value: boolean) => void) | null = null
  let disposed = false

  function settlePendingSpeak(value: boolean) {
    if (pendingSpeakResolve) {
      const resolve = pendingSpeakResolve
      pendingSpeakResolve = null
      resolve(value)
    }
  }

  async function init(preset: Live2DPresetInput): Promise<boolean> {
    if (model.value) return true
    if (initPromise) return initPromise

    disposed = false
    initPromise = (async () => {
      const stage = stageRef.value
      if (!stage) return false

      status.value = 'loading'
      errorMessage.value = ''

      try {
        app = new Application()
        await app.init({
          resizeTo: stage,
          preference: 'webgl',
          autoDensity: true,
          resolution: window.devicePixelRatio,
          backgroundAlpha: 0,
        })
        stage.appendChild(app.canvas)

        const instance = await Live2DModel.from(preset.url)

        // dispose() ran while we were awaiting Live2DModel.from(); bail out cleanly.
        if (disposed || !app) {
          instance.destroy({ children: true, texture: true, baseTexture: true })
          return false
        }

        // ponytail: fit once at init; the panel is a fixed 240px box, no resize observer
        const fit = Math.min(app.screen.width / instance.width, app.screen.height / instance.height)
        instance.scale.set(fit * (preset.zoom ?? 2.4))
        instance.anchor.set(0.5, preset.anchorY ?? 0.05)
        instance.position.set(app.screen.width / 2, 0)
        app.stage.addChild(instance)

        model.value = instance
        status.value = 'ready'
        return true
      } catch (error) {
        console.error('Live2D init failed:', error)
        model.value?.destroy({ children: true, texture: true, baseTexture: true })
        model.value = null
        app?.destroy(true)
        app = null
        status.value = 'error'
        errorMessage.value = error instanceof Error ? error.message : 'Avatar unavailable'
        return false
      } finally {
        initPromise = null
      }
    })()

    return initPromise
  }

  async function speak(audioUrl: string): Promise<boolean> {
    const instance = model.value
    if (!instance) return false

    status.value = 'speaking'
    return new Promise<boolean>((resolve) => {
      pendingSpeakResolve = resolve
      instance.speak(audioUrl, {
        onFinish: () => {
          settlePendingSpeak(true) // no-op if already settled by setIdle()/dispose()
          status.value = 'ready'
        },
        onError: (error: Error) => {
          console.error('Live2D speak failed:', error)
          settlePendingSpeak(false)
          status.value = 'ready'
        },
      })
    })
  }

  function setIdle() {
    if (status.value === 'speaking') {
      model.value?.stopSpeaking()
      settlePendingSpeak(false) // stopSpeaking() never fires onFinish/onError; unblock the awaiter
      status.value = model.value ? 'ready' : 'idle'
    }
  }

  function dispose() {
    disposed = true
    initPromise = null
    settlePendingSpeak(false)
    model.value?.destroy({ children: true, texture: true, baseTexture: true })
    model.value = null
    app?.destroy(true)
    app = null
    status.value = 'idle'
    errorMessage.value = ''
    stageRef.value?.replaceChildren()
  }

  return { status, errorMessage, init, speak, setIdle, dispose }
}
