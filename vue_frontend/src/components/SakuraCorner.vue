<script setup lang="ts">
import { useId } from 'vue'

withDefaults(
  defineProps<{
    class?: string
    size?: number
  }>(),
  { size: 72 },
)

const uid = useId()
const petalId = `sakura-petal-${uid}`
const centerId = `sakura-center-${uid}`
</script>

<template>
  <!-- Soft corner sakura: main blossom + trailing stem with two buds (bottom-right). -->
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 72 72"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    :class="['pointer-events-none absolute bottom-0 right-0 z-[1]', $props.class]"
    aria-hidden="true"
  >
    <defs>
      <radialGradient :id="petalId" cx="50%" cy="40%" r="70%">
        <stop offset="0%" stop-color="hsl(340 85% 88%)" stop-opacity="0.95" />
        <stop offset="100%" stop-color="hsl(340 70% 78%)" stop-opacity="0.55" />
      </radialGradient>
      <radialGradient :id="centerId" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="hsl(15 80% 78%)" />
        <stop offset="100%" stop-color="hsl(340 75% 72%)" />
      </radialGradient>
    </defs>

    <path
      d="M8 62 C22 60, 34 58, 44 52"
      stroke="hsl(340 55% 78%)"
      stroke-width="1.2"
      stroke-linecap="round"
      fill="none"
      opacity="0.7"
    />
    <ellipse
      cx="18"
      cy="60"
      rx="4"
      ry="3.2"
      :fill="`url(#${petalId})`"
      opacity="0.75"
      transform="rotate(-25 18 60)"
    />
    <ellipse
      cx="28"
      cy="58"
      rx="5"
      ry="4"
      :fill="`url(#${petalId})`"
      opacity="0.8"
      transform="rotate(-10 28 58)"
    />

    <g transform="translate(48 48)">
      <g transform="rotate(0)">
        <path
          d="M0 -2 C-5 -8,-7 -14,-3 -18 C-1.5 -19.5,0 -18.5,0 -17 C0 -18.5,1.5 -19.5,3 -18 C7 -14,5 -8,0 -2Z"
          :fill="`url(#${petalId})`"
        />
      </g>
      <g transform="rotate(72)">
        <path
          d="M0 -2 C-5 -8,-7 -14,-3 -18 C-1.5 -19.5,0 -18.5,0 -17 C0 -18.5,1.5 -19.5,3 -18 C7 -14,5 -8,0 -2Z"
          :fill="`url(#${petalId})`"
        />
      </g>
      <g transform="rotate(144)">
        <path
          d="M0 -2 C-5 -8,-7 -14,-3 -18 C-1.5 -19.5,0 -18.5,0 -17 C0 -18.5,1.5 -19.5,3 -18 C7 -14,5 -8,0 -2Z"
          :fill="`url(#${petalId})`"
        />
      </g>
      <g transform="rotate(216)">
        <path
          d="M0 -2 C-5 -8,-7 -14,-3 -18 C-1.5 -19.5,0 -18.5,0 -17 C0 -18.5,1.5 -19.5,3 -18 C7 -14,5 -8,0 -2Z"
          :fill="`url(#${petalId})`"
        />
      </g>
      <g transform="rotate(288)">
        <path
          d="M0 -2 C-5 -8,-7 -14,-3 -18 C-1.5 -19.5,0 -18.5,0 -17 C0 -18.5,1.5 -19.5,3 -18 C7 -14,5 -8,0 -2Z"
          :fill="`url(#${petalId})`"
        />
      </g>
      <circle r="3.2" :fill="`url(#${centerId})`" opacity="0.9" />
      <circle r="1.4" fill="hsl(340 60% 92%)" opacity="0.85" />
    </g>
  </svg>
</template>
