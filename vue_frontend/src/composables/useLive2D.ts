import { ref, shallowRef, type Ref } from 'vue'
import { Application, extensions, Rectangle } from 'pixi.js'
// Modern-only bundle (Cubism 3/4/5): needs just live2dcubismcore.min.js.
// The bare entry point also pulls in the Cubism 2 runtime and throws
// "requires live2d.min.js" at import time.
import { Live2DModel, Live2DPlugin, MotionPriority } from 'untitled-pixi-live2d-engine/cubism'
import { isLipSyncPayload, type LipSyncPayload } from '@/types/lipsync'
import { mouthOpenFromWords } from '@/lib/wordMouthSync'

extensions.add(Live2DPlugin)

const SNAPSHOT_RATIO_MIN = 0.25
const SNAPSHOT_RATIO_MAX = 8

/** Clamp photo scale ratio; invalid → undefined. */
function clampSnapshotRatio(value: number | undefined): number | undefined {
  if (value == null || !Number.isFinite(value) || value <= 0) return undefined
  return Math.min(SNAPSHOT_RATIO_MAX, Math.max(SNAPSHOT_RATIO_MIN, value))
}

/**
 * Pixi extract.resolution for a CSS-space frame (app.screen).
 * Output pixels ≈ screenCss × ratio — independent of devicePixelRatio.
 * Must always be passed explicitly; omitting lets Pixi default to renderer.resolution (DPR).
 */
export function snapshotExtractResolution(ratio?: number): number | undefined {
  return clampSnapshotRatio(ratio)
}

/** Minimal shape of @pixi/sound Sound used for word-timed mouth sync. */
type PlayingSound = {
  isPlaying: boolean
  duration: number
  instances: { progress: number }[]
}

type MouthSyncMotionManager = {
  mouthSync: () => number
  currentAudio?: PlayingSound
}

type LipSyncOptions = {
  lipSyncGain?: number
  lipSyncWeight?: number
}

export type Live2DStatus = 'idle' | 'loading' | 'ready' | 'speaking' | 'error'

export type Live2DPresetInput = {
  url: string
  zoom?: number // extra zoom on top of fit-to-panel; default 2.4 (upper-body framing)
  anchorY?: number // vertical anchor 0..1 from model top; default 0.05
  offsetX?: number // px added after fit; default 0
  offsetY?: number // px added after fit; default 0
  // Shared-stage layout: the canvas spans all slots and the model is fitted to
  // and centered in its own slot column, so it can overdraw without clipping.
  slots?: number // horizontal slot count; default 1 (model owns the whole canvas)
  slot?: number // this model's slot index; default 0
}

export type Live2DInitOptions = {
  /** Track pointer for eye/head look-at. Default true (engine default). */
  autoFocus?: boolean
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

/** Cubism moc owned by InternalModel; engine never decrements _modelCount before release. */
type CubismMocRef = { _modelCount: number }

/**
 * Destroy a Live2D model without tripping CubismMoc.release()'s CSM_ASSERT(_modelCount == 0).
 * untitled-pixi-live2d-engine increments _modelCount in createModel() but releaseMoc never
 * calls deleteModel(), so every destroy would otherwise console.assert.
 * Do not pass texture/baseTexture:true — textures are Pixi Assets-managed.
 */
function destroyLive2DModel(instance: Live2DModel) {
  const moc = (instance.internalModel as unknown as { __moc?: CubismMocRef }).__moc
  if (moc) moc._modelCount = 0
  instance.destroy({ children: true })
}

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
  let restoreMouthSync: (() => void) | null = null
  let resizeObserver: ResizeObserver | null = null
  let disposed = false
  /** Bumped on dispose() and at each init() start; stale awaits bail when gen mismatches. */
  let loadGen = 0
  let activePreset: Live2DPresetInput | null = null

  /** Fit-to-stage plus preset zoom; safe to re-run whenever the stage resizes. */
  function fitModel(instance: Live2DModel, preset: Live2DPresetInput) {
    if (!app) return
    // PIXI width/height are scale-dependent; measure at scale 1 so refits don't compound.
    instance.scale.set(1)
    const slots = preset.slots ?? 1
    const slot = preset.slot ?? 0
    const fit = Math.min(
      app.screen.width / slots / instance.width,
      app.screen.height / instance.height,
    )
    instance.scale.set(fit * (preset.zoom ?? 2.4))
    instance.anchor.set(0.5, preset.anchorY ?? 0.05)
    instance.position.set(
      ((slot + 0.5) / slots) * app.screen.width + (preset.offsetX ?? 0),
      preset.offsetY ?? 0,
    )
  }

  function clearWordMouthSync() {
    restoreMouthSync?.()
    restoreMouthSync = null
  }

  /** Drive engine mouthSync() from word timings instead of audio amplitude. */
  function installWordMouthSync(instance: Live2DModel, lipsync: LipSyncPayload) {
    clearWordMouthSync()
    const mm = instance.internalModel.motionManager as unknown as MouthSyncMotionManager
    const options = instance.internalModel.options as LipSyncOptions
    const prevGain = options.lipSyncGain
    const prevWeight = options.lipSyncWeight
    const originalMouthSync = mm.mouthSync

    // Word pulses are already 0..1; amplitude defaults (2.5 / 1.0) would clamp wide open.
    options.lipSyncGain = 1.0
    options.lipSyncWeight = 1.0

    mm.mouthSync = () => {
      const audio = mm.currentAudio
      if (!audio?.isPlaying) return 0
      const inst = audio.instances[0]
      if (!inst) return 0
      const tMs = inst.progress * (audio.duration || 0) * 1000
      return mouthOpenFromWords(tMs, lipsync)
    }

    restoreMouthSync = () => {
      mm.mouthSync = originalMouthSync
      options.lipSyncGain = prevGain
      options.lipSyncWeight = prevWeight
    }
  }

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

  /** Re-apply fit math with a new preset (e.g. zoom change) without reloading the model. */
  function refit(preset: Live2DPresetInput) {
    activePreset = preset
    if (model.value) fitModel(model.value, preset)
  }

  async function init(
    preset: Live2DPresetInput,
    options?: Live2DInitOptions,
  ): Promise<boolean> {
    if (model.value) return true
    if (initPromise) return initPromise

    disposed = false
    const gen = ++loadGen
    activePreset = preset
    const autoFocus = options?.autoFocus ?? true
    const thisInit = (async () => {
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

        // dispose()/newer init invalidated this attempt while awaiting app.init().
        if (disposed || gen !== loadGen || !app) return false
        stage.appendChild(app.canvas)

        // Defaults (1.5 / 0.4) keep mouths too closed; weight 1.0 applies full open amount.
        const instance = await Live2DModel.from(preset.url, {
          lipSyncGain: 2.5,
          lipSyncWeight: 1.0,
          autoFocus,
        })

        // dispose()/newer init ran while awaiting from(); bail without attaching.
        // Do not destroy textures — Live2DModel.from() registers them in Pixi Assets;
        // destroying TextureSources poisons the cache for later loads of the same URL
        // (partner-select → in-game reuse).
        if (disposed || gen !== loadGen || !app) {
          destroyLive2DModel(instance)
          return false
        }

        fitModel(instance, activePreset ?? preset)
        app.stage.addChild(instance)

        // The game stage is viewport-sized; refit on stage resize. resizeTo only
        // tracks window resize, so sync the renderer first for element-only resizes.
        if (typeof ResizeObserver !== 'undefined') {
          resizeObserver = new ResizeObserver(() => {
            app?.resize()
            fitModel(instance, activePreset ?? preset)
          })
          resizeObserver.observe(stage)
        }

        model.value = instance
        capabilities.value = readCapabilities(instance)
        status.value = 'ready'
        return true
      } catch (error) {
        console.error('Live2D init failed:', error)
        if (model.value) destroyLive2DModel(model.value)
        model.value = null
        app?.destroy(true)
        app = null
        status.value = 'error'
        errorMessage.value = error instanceof Error ? error.message : 'Avatar unavailable'
        return false
      } finally {
        // Only clear if we still own the slot — a newer init() after dispose() must keep its promise.
        if (initPromise === thisInit) initPromise = null
      }
    })()
    initPromise = thisInit

    return thisInit
  }

  /** Enable/disable pointer look-at; when disabling, snap gaze to face the camera. */
  function setAutoFocus(enabled: boolean) {
    const instance = model.value
    if (!instance) return
    instance.automator.autoFocus = enabled
    if (!enabled) {
      // Live2DModel.focus(x,y) is world-space — (0,0) is stage top-left, not "forward".
      // FocusController uses normalized [-1,1]; (0,0) faces the camera.
      instance.internalModel.focusController.focus(0, 0, true)
    }
  }

  async function speak(audioUrl: string, lipsync?: LipSyncPayload | null): Promise<boolean> {
    const instance = model.value
    if (!instance) return false

    settlePendingSpeak(false) // supersede any still-pending speak from this instance
    clearWordMouthSync()
    if (lipsync && isLipSyncPayload(lipsync)) {
      installWordMouthSync(instance, lipsync)
    }

    status.value = 'speaking'
    return new Promise<boolean>((resolve) => {
      pendingSpeakResolve = resolve
      instance.speak(audioUrl, {
        onFinish: () => {
          clearWordMouthSync()
          settlePendingSpeak(true) // no-op if already settled by setIdle()/dispose()
          status.value = 'ready'
        },
        onError: (error: Error) => {
          console.error('Live2D speak failed:', error)
          clearWordMouthSync()
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
    // This call's own settle; onError must not touch the shared slot, or a stale
    // audio error from a superseded motion would settle the NEWER call's promise.
    let localSettle: ((value: boolean) => void) | null = null

    let started: boolean
    try {
      started = await instance.motion(group, index, MotionPriority.FORCE, {
        // Every official sample motion has Loop:true in its motion3.json; a looping
        // motion never finishes, so 'motionFinish' would never fire. loop:false
        // overrides the JSON metadata → play once, then resolve.
        loop: false,
        onError: (error: Error) => {
          console.error('Live2D motion failed:', error)
          localSettle?.(false)
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
        localSettle = null
        manager.off('motionFinish', onMotionFinish)
        resolve(value)
      }
      pendingMotionSettle = settle
      localSettle = settle
      manager.once('motionFinish', onMotionFinish)
    })
  }

  /** Stop the current FORCE motion (if any) and settle a pending playMotion promise. */
  function stopMotion() {
    const instance = model.value
    if (!instance) {
      settlePendingMotion(false)
      return
    }
    const manager = instance.internalModel.motionManager as unknown as {
      stopAllMotions?: () => void
    }
    manager.stopAllMotions?.()
    settlePendingMotion(false)
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
      clearWordMouthSync()
      settlePendingSpeak(false) // stopSpeaking() never fires onFinish/onError; unblock the awaiter
      status.value = model.value ? 'ready' : 'idle'
    }
  }

  /**
   * Download the current stage as a PNG with transparent background.
   * Uses Pixi extract (not DOM screenshot) so CSS card chrome is omitted.
   * Ratio multiplies stage CSS size: output ≈ screenCss × ratio (DPR-independent).
   */
  function downloadSnapshot(filename = 'avatar.png', ratio = 1): boolean {
    if (!app || !model.value) return false
    try {
      const renderW = app.renderer.width
      const renderH = app.renderer.height
      const dpr = app.renderer.resolution
      const screenW = app.screen.width
      const screenH = app.screen.height
      const scale = clampSnapshotRatio(ratio) ?? 1
      // Always set resolution explicitly — Pixi's default is renderer.resolution (DPR).
      const resolution = scale
      const extractOptions = {
        target: app.stage,
        filename,
        frame: new Rectangle(0, 0, screenW, screenH),
        clearColor: [0, 0, 0, 0] as [number, number, number, number],
        antialias: true,
        resolution,
      }
      console.debug('[Live2D snapshot]', {
        filename,
        ratio: scale,
        renderPx: { width: renderW, height: renderH },
        screenCssPx: { width: screenW, height: screenH },
        rendererResolution: dpr,
        extractResolution: resolution,
        expectedOutputPx: {
          width: Math.round(screenW * scale),
          height: Math.round(screenH * scale),
        },
        extractOptions: {
          filename: extractOptions.filename,
          frame: { x: 0, y: 0, width: screenW, height: screenH },
          clearColor: extractOptions.clearColor,
          antialias: extractOptions.antialias,
          resolution: extractOptions.resolution,
        },
      })
      app.renderer.extract.download(extractOptions)
      return true
    } catch (error) {
      console.error('Live2D snapshot failed:', error)
      return false
    }
  }

  function dispose() {
    disposed = true
    loadGen++
    initPromise = null
    resizeObserver?.disconnect()
    resizeObserver = null
    clearWordMouthSync()
    settlePendingSpeak(false)
    settlePendingMotion(false)
    // Teardown may race an in-flight init() (renderer mid-init); never let a
    // throw here abort a disposeAll() loop over sibling panels.
    //
    // Never pass texture/baseTexture:true — textures are Assets-managed. Partner
    // select and in-game panels load the same model URLs; destroying TextureSources
    // leaves the Assets cache holding dead entries and the next from() render
    // crashes (pixelWidth of null).
    try {
      app?.ticker.stop()
      const instance = model.value
      if (instance && app) {
        app.stage.removeChild(instance)
      }
      if (instance) destroyLive2DModel(instance)
      app?.destroy(true)
    } catch (error) {
      console.error('Live2D dispose failed:', error)
    }
    model.value = null
    capabilities.value = null
    app = null
    activePreset = null
    status.value = 'idle'
    errorMessage.value = ''
    stageRef.value?.replaceChildren()
  }

  return {
    status,
    errorMessage,
    capabilities,
    init,
    refit,
    speak,
    playMotion,
    stopMotion,
    setExpression,
    resetExpression,
    setIdle,
    setAutoFocus,
    downloadSnapshot,
    dispose,
  }
}
