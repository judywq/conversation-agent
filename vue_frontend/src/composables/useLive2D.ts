import { ref, shallowRef, type Ref } from 'vue'
import { Application, extensions } from 'pixi.js'
// Modern-only bundle (Cubism 3/4/5): needs just live2dcubismcore.min.js.
// The bare entry point also pulls in the Cubism 2 runtime and throws
// "requires live2d.min.js" at import time.
import { Live2DModel, Live2DPlugin, MotionPriority } from 'untitled-pixi-live2d-engine/cubism'

extensions.add(Live2DPlugin)

export type Live2DStatus = 'idle' | 'loading' | 'ready' | 'speaking' | 'error'

export type Live2DPresetInput = {
  url: string
  zoom?: number // extra zoom on top of fit-to-panel; default 2.4 (upper-body framing)
  anchorY?: number // vertical anchor 0..1 from model top; default 0.05
}

export type Live2DMotionEntry = { index: number; name: string }

export type Live2DCapabilities = {
  motionGroups: { group: string; motions: Live2DMotionEntry[] }[]
  expressions: string[]
  idleGroup: string
}

// The abstract managers type their specs as `unknown`; these are the Cubism 3/4/5 manifest shapes.
type MotionSpec = { File: string; Name?: string }
type ExpressionSpec = { Name: string }

function readCapabilities(instance: Live2DModel): Live2DCapabilities {
  const manager = instance.internalModel.motionManager
  const definitions = manager.definitions as Partial<Record<string, MotionSpec[]>>
  const motionGroups = Object.entries(definitions).map(([group, specs]) => ({
    group,
    motions: (specs ?? []).map((spec, index) => ({
      index,
      // Manifest motion entries rarely carry a Name; fall back to the file basename.
      name: spec.Name ?? spec.File.replace(/^.*\//, '').replace(/\.motion3\.json$/, ''),
    })),
  }))
  const expressions = (
    (manager.expressionManager?.definitions ?? []) as ExpressionSpec[]
  ).map((spec) => spec.Name)
  return { motionGroups, expressions, idleGroup: manager.groups.idle }
}

export function useLive2D(stageRef: Ref<HTMLElement | null>) {
  const status = ref<Live2DStatus>('idle')
  const errorMessage = ref('')
  const capabilities = ref<Live2DCapabilities | null>(null)
  const model = shallowRef<Live2DModel | null>(null)
  let app: Application | null = null
  let initPromise: Promise<boolean> | null = null
  let pendingSpeakResolve: ((value: boolean) => void) | null = null
  let pendingMotionSettle: ((value: boolean) => void) | null = null
  let disposed = false

  function settlePendingSpeak(value: boolean) {
    if (pendingSpeakResolve) {
      const resolve = pendingSpeakResolve
      pendingSpeakResolve = null
      resolve(value)
    }
  }

  function settlePendingMotion(value: boolean) {
    if (pendingMotionSettle) {
      const settle = pendingMotionSettle
      pendingMotionSettle = null
      settle(value)
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

        // dispose() ran while we were awaiting app.init(); bail before touching app.
        if (disposed || !app) return false
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
        capabilities.value = readCapabilities(instance)
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

    settlePendingSpeak(false) // supersede any still-pending speak from this instance
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

  async function playMotion(group: string, index: number): Promise<boolean> {
    const instance = model.value
    if (!instance) return false

    settlePendingMotion(false) // supersede any still-pending motion (e.g. a second Play click)

    // FORCE so debug clicks always preempt the idle loop. motion() only reports
    // whether the motion STARTED; onFinish is audio-gated and never fires for our
    // sample models (no Sound field), and a later FORCE preemption can drop it
    // even when audio is present — so completion comes from the motion manager's
    // 'motionFinish' event instead (see below).
    let started: boolean
    try {
      started = await instance.motion(group, index, MotionPriority.FORCE, {
        // Every official sample motion has Loop:true in its motion3.json; a looping
        // motion never finishes, so 'motionFinish' would never fire. loop:false
        // overrides the JSON metadata → play once, then resolve.
        loop: false,
        onError: (error: Error) => {
          console.error('Live2D motion failed:', error)
          settlePendingMotion(false)
        },
      })
    } catch {
      return false
    }
    if (!started) return false

    return new Promise<boolean>((resolve) => {
      // 'motionFinish' is emitted by MotionManager.update() when the current motion
      // completes, but is absent from the typed event map — hence the local cast.
      const manager = instance.internalModel.motionManager as unknown as {
        once(event: string, fn: () => void): void
        off(event: string, fn: () => void): void
      }
      const onMotionFinish = () => settle(true)
      function settle(value: boolean) {
        pendingMotionSettle = null
        manager.off('motionFinish', onMotionFinish)
        resolve(value)
      }
      pendingMotionSettle = settle
      manager.once('motionFinish', onMotionFinish)
    })
  }

  async function setExpression(id: string | number): Promise<boolean> {
    const instance = model.value
    if (!instance) return false
    return instance.expression(id)
  }

  function resetExpression() {
    model.value?.internalModel.motionManager.expressionManager?.resetExpression()
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
    settlePendingMotion(false)
    // Teardown may race an in-flight init() (renderer mid-init); never let a
    // throw here abort a disposeAll() loop over sibling panels.
    try {
      model.value?.destroy({ children: true, texture: true, baseTexture: true })
      app?.destroy(true)
    } catch (error) {
      console.error('Live2D dispose failed:', error)
    }
    model.value = null
    capabilities.value = null
    app = null
    status.value = 'idle'
    errorMessage.value = ''
    stageRef.value?.replaceChildren()
  }

  return {
    status,
    errorMessage,
    capabilities,
    init,
    speak,
    playMotion,
    setExpression,
    resetExpression,
    setIdle,
    dispose,
  }
}
