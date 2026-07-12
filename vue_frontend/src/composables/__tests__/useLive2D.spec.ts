import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const fakeModel = {
  width: 1000,
  height: 2000,
  scale: { set: vi.fn() },
  anchor: { set: vi.fn() },
  position: { set: vi.fn() },
  speak: vi.fn(),
  stopSpeaking: vi.fn(),
  destroy: vi.fn(),
}

const appInstance = {
  init: vi.fn().mockResolvedValue(undefined),
  canvas: null as HTMLCanvasElement | null,
  screen: { width: 360, height: 240 },
  stage: { addChild: vi.fn() },
  destroy: vi.fn(),
}

vi.mock('pixi.js', () => ({
  Application: vi.fn().mockImplementation(() => {
    appInstance.canvas = document.createElement('canvas')
    return appInstance
  }),
  extensions: { add: vi.fn() },
}))

vi.mock('untitled-pixi-live2d-engine/cubism', () => ({
  Live2DPlugin: {},
  Live2DModel: { from: vi.fn() },
}))

import { Live2DModel } from 'untitled-pixi-live2d-engine/cubism'
import { useLive2D } from '../useLive2D'

function makeStage() {
  return ref<HTMLElement | null>(document.createElement('div'))
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(Live2DModel.from as ReturnType<typeof vi.fn>).mockResolvedValue(fakeModel)
})

describe('useLive2D', () => {
  it('init loads the model and reaches ready', async () => {
    const { init, status } = useLive2D(makeStage())
    await expect(init({ url: '/live2d/x/runtime/x.model3.json' })).resolves.toBe(true)
    expect(status.value).toBe('ready')
    expect(Live2DModel.from).toHaveBeenCalledWith('/live2d/x/runtime/x.model3.json')
  })

  it('init returns false when stage element is missing', async () => {
    const { init, status } = useLive2D(ref<HTMLElement | null>(null))
    await expect(init({ url: '/m.model3.json' })).resolves.toBe(false)
    expect(status.value).toBe('idle')
  })

  it('init failure sets error status and message', async () => {
    ;(Live2DModel.from as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('404'))
    const { init, status, errorMessage } = useLive2D(makeStage())
    await expect(init({ url: '/m.model3.json' })).resolves.toBe(false)
    expect(status.value).toBe('error')
    expect(errorMessage.value).toBe('404')
  })

  it('speak before init resolves false', async () => {
    const { speak } = useLive2D(makeStage())
    await expect(speak('/audio.mp3')).resolves.toBe(false)
  })

  it('speak resolves true on onFinish and returns to ready', async () => {
    fakeModel.speak.mockImplementation((_url: string, opts: { onFinish: () => void }) =>
      opts.onFinish(),
    )
    const { init, speak, status } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    await expect(speak('/audio.mp3')).resolves.toBe(true)
    expect(status.value).toBe('ready')
  })

  it('speak resolves false on onError', async () => {
    fakeModel.speak.mockImplementation(
      (_url: string, opts: { onError: (e: unknown) => void }) => opts.onError(new Error('bad')),
    )
    const { init, speak, status } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    await expect(speak('/audio.mp3')).resolves.toBe(false)
    expect(status.value).toBe('ready')
  })

  it('setIdle stops speaking', async () => {
    const { init, setIdle, status } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    status.value = 'speaking'
    setIdle()
    expect(fakeModel.stopSpeaking).toHaveBeenCalled()
    expect(status.value).toBe('ready')
  })

  it('dispose destroys the app and resets state', async () => {
    const { init, dispose, status } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    dispose()
    expect(appInstance.destroy).toHaveBeenCalled()
    expect(status.value).toBe('idle')
  })

  it('setIdle settles an in-flight speak() with false when the engine never calls onFinish/onError', async () => {
    // stopSpeaking() (called by setIdle) does not invoke onFinish/onError, so the engine
    // mock here intentionally never calls either — mirrors a barge-in/stop mid-utterance.
    fakeModel.speak.mockImplementation(() => {})
    const { init, speak, setIdle, status } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    const speakPromise = speak('/audio.mp3')
    expect(status.value).toBe('speaking')
    setIdle()
    await expect(speakPromise).resolves.toBe(false)
    expect(fakeModel.stopSpeaking).toHaveBeenCalled()
  })

  it('dispose settles an in-flight speak() with false when the engine never calls onFinish/onError', async () => {
    fakeModel.speak.mockImplementation(() => {})
    const { init, speak, dispose } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    const speakPromise = speak('/audio.mp3')
    dispose()
    await expect(speakPromise).resolves.toBe(false)
  })

  it('dispose during in-flight init bails cleanly without error state', async () => {
    const { init, dispose, status } = useLive2D(makeStage())
    const initPromise = init({ url: '/m.model3.json' })
    dispose() // lands while init is still awaiting app.init()/model load
    await expect(initPromise).resolves.toBe(false)
    expect(status.value).toBe('idle') // not overwritten with 'error'
  })
})
