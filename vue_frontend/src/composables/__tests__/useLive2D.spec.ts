import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const resetExpressionMock = vi.fn()

const fakeModel = {
  width: 1000,
  height: 2000,
  scale: { set: vi.fn() },
  anchor: { set: vi.fn() },
  position: { set: vi.fn() },
  speak: vi.fn(),
  stopSpeaking: vi.fn(),
  destroy: vi.fn(),
  motion: vi.fn(),
  expression: vi.fn(),
  internalModel: {
    motionManager: {
      definitions: {
        Idle: [{ File: 'motions/Hiyori_m01.motion3.json' }, { File: 'motions/Hiyori_m02.motion3.json' }],
        TapBody: [{ File: 'motions/Hiyori_m04.motion3.json', Name: 'Wave' }],
      },
      groups: { idle: 'Idle' },
      expressionManager: {
        definitions: [{ Name: 'F01' }, { Name: 'F02' }],
        resetExpression: resetExpressionMock,
      },
    },
  },
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
  MotionPriority: { NONE: 0, IDLE: 1, NORMAL: 2, FORCE: 3 },
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

  it('exposes capabilities after init, named from Name or file basename', async () => {
    const { init, capabilities } = useLive2D(makeStage())
    expect(capabilities.value).toBeNull()
    await init({ url: '/m.model3.json' })
    expect(capabilities.value).toEqual({
      motionGroups: [
        {
          group: 'Idle',
          motions: [
            { index: 0, name: 'Hiyori_m01' },
            { index: 1, name: 'Hiyori_m02' },
          ],
        },
        { group: 'TapBody', motions: [{ index: 0, name: 'Wave' }] },
      ],
      expressions: ['F01', 'F02'],
      idleGroup: 'Idle',
    })
  })

  it('reports empty expressions when the model has no expressionManager', async () => {
    const bare = {
      ...fakeModel,
      internalModel: {
        motionManager: {
          definitions: { Idle: [{ File: 'a.motion3.json' }] },
          groups: { idle: 'Idle' },
          expressionManager: undefined,
        },
      },
    }
    ;(Live2DModel.from as ReturnType<typeof vi.fn>).mockResolvedValue(bare)
    const { init, capabilities } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    expect(capabilities.value?.expressions).toEqual([])
  })

  it('playMotion resolves true when the motion finishes', async () => {
    fakeModel.motion.mockImplementation(
      (_g: string, _i: number, _p: number, opts: { onFinish: () => void }) => {
        opts.onFinish()
        return Promise.resolve(true)
      },
    )
    const { init, playMotion } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    await expect(playMotion('TapBody', 0)).resolves.toBe(true)
    expect(fakeModel.motion).toHaveBeenCalledWith('TapBody', 0, 3, expect.any(Object))
  })

  it('playMotion resolves false when the engine refuses to start the motion', async () => {
    fakeModel.motion.mockResolvedValue(false) // never calls onFinish
    const { init, playMotion } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    await expect(playMotion('TapBody', 0)).resolves.toBe(false)
  })

  it('playMotion and setExpression resolve false before init', async () => {
    const { playMotion, setExpression } = useLive2D(makeStage())
    await expect(playMotion('Idle', 0)).resolves.toBe(false)
    await expect(setExpression('F01')).resolves.toBe(false)
  })

  it('setExpression delegates to model.expression', async () => {
    fakeModel.expression.mockResolvedValue(true)
    const { init, setExpression } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    await expect(setExpression('F02')).resolves.toBe(true)
    expect(fakeModel.expression).toHaveBeenCalledWith('F02')
  })

  it('resetExpression calls the expression manager and tolerates models without one', async () => {
    const { init, resetExpression } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    resetExpression()
    expect(resetExpressionMock).toHaveBeenCalled()
    // no model loaded → must be a silent no-op, not a throw
    const { resetExpression: resetBeforeInit } = useLive2D(makeStage())
    expect(() => resetBeforeInit()).not.toThrow()
  })

  it('dispose clears capabilities', async () => {
    const { init, dispose, capabilities } = useLive2D(makeStage())
    await init({ url: '/m.model3.json' })
    dispose()
    expect(capabilities.value).toBeNull()
  })
})
