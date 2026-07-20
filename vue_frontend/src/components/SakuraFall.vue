<script setup lang="ts">
import { sakuraFallEnabled } from '@/composables/useSakuraFall'

type Petal = {
  id: number
  left: string
  size: string
  duration: string
  delay: string
  drift: string
  spin: string
  peakOpacity: string
}

function rand(min: number, max: number) {
  return min + Math.random() * (max - min)
}

// --- Petal field density & layout -------------------------------------------

/** How many petals exist at once across the viewport. */
const PETAL_COUNT = 8

/**
 * Horizontal spawn range as % of viewport width.
 * 0 = left edge, 100 = right edge.
 */
const LEFT_MIN_PCT = 0
const LEFT_MAX_PCT = 100

/**
 * Petal width in px (height is derived via PETAL_HEIGHT_RATIO).
 * Larger = bigger blossoms.
 */
const SIZE_MIN_PX = 10
const SIZE_MAX_PX = 20

/** Height as a fraction of width (petal shape is slightly flatter than square). */
const PETAL_HEIGHT_RATIO = 0.75

/**
 * Distance above the viewport where petals spawn (px).
 * Keeps them off-screen until the fall starts.
 */
const SPAWN_TOP_OFFSET_PX = 24

// --- Fall timing ------------------------------------------------------------

/**
 * One full fall cycle length in seconds.
 * Longer = slower, gentler drift.
 */
const DURATION_MIN_S = 8
const DURATION_MAX_S = 16

/**
 * Animation start offset as a fraction of that petal's duration.
 * Negative delay (0 … duration) means petals are already mid-fall on load
 * instead of all spawning at the top together.
 */
const DELAY_MIN_FRAC = 0
const DELAY_MAX_FRAC = 1

// --- Motion & look ----------------------------------------------------------

/**
 * Horizontal sway over one fall, in px.
 * Negative = drift left, positive = drift right.
 */
const DRIFT_MIN_PX = -360
const DRIFT_MAX_PX = 360

/**
 * Total rotation over one fall, in degrees.
 * Higher range = more tumbling variety.
 */
const SPIN_MIN_DEG = 280
const SPIN_MAX_DEG = 520

/**
 * Peak opacity while the petal is mid-fall (0–1).
 * Lower = subtler; higher = more visible.
 */
const PEAK_OPACITY_MIN = 0.65
const PEAK_OPACITY_MAX = 0.95

/**
 * How far down the petal travels, as a CSS length.
 * 110vh ends slightly past the bottom of the screen.
 */
const FALL_DISTANCE = '110vh'

const petals: Petal[] = Array.from({ length: PETAL_COUNT }, (_, id) => {
  const duration = rand(DURATION_MIN_S, DURATION_MAX_S)
  return {
    id,
    left: `${rand(LEFT_MIN_PCT, LEFT_MAX_PCT).toFixed(2)}%`,
    size: `${rand(SIZE_MIN_PX, SIZE_MAX_PX).toFixed(1)}px`,
    duration: `${duration.toFixed(2)}s`,
    delay: `${(-rand(DELAY_MIN_FRAC, DELAY_MAX_FRAC) * duration).toFixed(2)}s`,
    drift: `${rand(DRIFT_MIN_PX, DRIFT_MAX_PX).toFixed(0)}px`,
    spin: `${rand(SPIN_MIN_DEG, SPIN_MAX_DEG).toFixed(0)}deg`,
    peakOpacity: rand(PEAK_OPACITY_MIN, PEAK_OPACITY_MAX).toFixed(2),
  }
})
</script>

<template>
  <div
    v-if="sakuraFallEnabled"
    class="sakura-fall pointer-events-none overflow-hidden"
    aria-hidden="true"
    :style="{
      '--spawn-top': `-${SPAWN_TOP_OFFSET_PX}px`,
      '--fall-distance': FALL_DISTANCE,
    }"
  >
    <span
      v-for="petal in petals"
      :key="petal.id"
      class="sakura-fall__petal"
      :style="{
        left: petal.left,
        width: petal.size,
        height: `calc(${petal.size} * ${PETAL_HEIGHT_RATIO})`,
        '--dur': petal.duration,
        '--delay': petal.delay,
        '--drift': petal.drift,
        '--spin': petal.spin,
        '--peak': petal.peakOpacity,
      }"
    />
  </div>
</template>

<style scoped>
.sakura-fall__petal {
  position: absolute;
  top: var(--spawn-top);
  border-radius: 70% 0 70% 0;
  background: hsl(340 75% 82% / 0.9);
  box-shadow: 0 0 5px hsl(340 80% 88% / 0.45);
  opacity: 0;
  will-change: transform, opacity;
  animation: sakura-fall-drift var(--dur) linear infinite;
  animation-delay: var(--delay);
}

.sakura-fall__petal:nth-child(odd) {
  background: hsl(350 70% 88% / 0.85);
}

.sakura-fall__petal:nth-child(3n) {
  background: hsl(335 80% 86% / 0.8);
}

@keyframes sakura-fall-drift {
  0% {
    transform: translate3d(0, 0, 0) rotate(0deg);
    opacity: 0;
  }
  8% {
    opacity: var(--peak);
  }
  85% {
    opacity: var(--peak);
  }
  100% {
    transform: translate3d(var(--drift), var(--fall-distance), 0) rotate(var(--spin));
    opacity: 0;
  }
}
</style>
