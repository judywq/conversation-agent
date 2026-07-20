import { useStorage } from '@vueuse/core'

/** Persisted sakura fall preference (default on). Shared across layouts + game. */
export const sakuraFallEnabled = useStorage('conv-sakura-fall', true)
