<script setup lang="ts">
import { partnerCardBgUrl } from '@/config/partnerCardBgs'
import { PARTNER_THUMB_PLACEHOLDER, partnerThumbUrl } from '@/config/partnerThumbs'
import type { AgentCharacter } from '@/services/conversationService'
import { AudioLines, Check } from 'lucide-vue-next'
import { computed, ref } from 'vue'

/** Max rotation (degrees) at the card edge; center stays flat. */
const TILT_MAX_DEG = 8
/** CSS perspective distance (px); lower = stronger 3D depth. */
const TILT_PERSPECTIVE_PX = 900
/** Scale applied while the pointer is over the card. */
const TILT_SCALE = 1.02
/** Duration (ms) for transform to ease back when the pointer leaves. */
const TILT_RESET_MS = 200
/** Blur (px) on the decorative background. */
const BG_BLUR_PX = 1
/** Background scale at rest (slightly oversize so blur edges stay clipped). */
const BG_SCALE = 1.08
/** Background scale while the pointer is over the card. */
const BG_HOVER_SCALE = 1.18
/** Duration (ms) for background zoom in/out. */
const BG_ZOOM_MS = 300
/** Enter zoom curve: fast rise, then soft settle (approx. expo-out). */
const BG_ZOOM_ENTER_EASE = 'cubic-bezier(0.16, 1, 0.3, 1)'
/** Leave zoom curve. */
const BG_ZOOM_LEAVE_EASE = 'ease-out'
/** Max bg translate (px) opposite the pointer — farther layer. */
const PARALLAX_BG_PX = 6
/** Max character translate (px) toward the pointer — nearer layer. */
const PARALLAX_FG_PX = 3

const props = defineProps<{
  character: AgentCharacter
  backgroundIndex: number
  selected: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

const cardRef = ref<HTMLButtonElement | null>(null)
const rotateX = ref(0)
const rotateY = ref(0)
const scale = ref(1)
const tilting = ref(false)
const bgHovered = ref(false)
/** Normalized pointer offset from center, range [-1, 1]. */
const parallaxX = ref(0)
const parallaxY = ref(0)

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const isInteractionLocked = computed(() => props.disabled && !props.selected)

const layerTransition = computed(() =>
  tilting.value ? 'none' : `transform ${TILT_RESET_MS}ms ease-out`,
)

const tiltStyle = computed(() => ({
  transform: `perspective(${TILT_PERSPECTIVE_PX}px) rotateX(${rotateX.value}deg) rotateY(${rotateY.value}deg) scale3d(${scale.value}, ${scale.value}, ${scale.value})`,
  transition: tilting.value
    ? 'box-shadow 150ms ease, border-color 150ms ease'
    : `transform ${TILT_RESET_MS}ms ease-out, box-shadow 150ms ease, border-color 150ms ease`,
}))

const bgParallaxStyle = computed(() => {
  const tx = parallaxX.value * -PARALLAX_BG_PX
  const ty = parallaxY.value * -PARALLAX_BG_PX
  return {
    transform: `translate(${tx}px, ${ty}px)`,
    transition: layerTransition.value,
  }
})

const bgZoomStyle = computed(() => {
  const zoom =
    bgHovered.value && !isInteractionLocked.value && !prefersReducedMotion()
      ? BG_HOVER_SCALE
      : BG_SCALE
  return {
    backgroundImage: `url(${partnerCardBgUrl(props.backgroundIndex)})`,
    filter: `blur(${BG_BLUR_PX}px)`,
    transform: `scale(${zoom})`,
    // Expo-out on enter (jumps then settles); ease-out on leave
    transition: `transform ${BG_ZOOM_MS}ms ${bgHovered.value ? BG_ZOOM_ENTER_EASE : BG_ZOOM_LEAVE_EASE}`,
  }
})

const fgStyle = computed(() => {
  const tx = parallaxX.value * PARALLAX_FG_PX
  const ty = parallaxY.value * PARALLAX_FG_PX
  return {
    transform: `translate(${tx}px, ${ty}px)`,
    transition: layerTransition.value,
  }
})

function resetMotion() {
  tilting.value = false
  rotateX.value = 0
  rotateY.value = 0
  scale.value = 1
  parallaxX.value = 0
  parallaxY.value = 0
}

function onMouseEnter() {
  if (isInteractionLocked.value) return
  bgHovered.value = true
}

function onMouseMove(event: MouseEvent) {
  if (isInteractionLocked.value || prefersReducedMotion()) return
  const el = cardRef.value
  if (!el) return

  tilting.value = true
  const rect = el.getBoundingClientRect()
  const nx = ((event.clientX - rect.left) / rect.width - 0.5) * 2
  const ny = ((event.clientY - rect.top) / rect.height - 0.5) * 2
  rotateY.value = nx * TILT_MAX_DEG
  rotateX.value = -ny * TILT_MAX_DEG
  scale.value = TILT_SCALE
  parallaxX.value = nx
  parallaxY.value = ny
}

function onMouseLeave() {
  bgHovered.value = false
  resetMotion()
}

function onThumbError(event: Event) {
  const img = event.target as HTMLImageElement
  if (img.src.endsWith(PARTNER_THUMB_PLACEHOLDER)) return
  img.src = PARTNER_THUMB_PLACEHOLDER
}

function onClick() {
  if (isInteractionLocked.value) return
  emit('toggle')
}
</script>

<template>
  <button
    ref="cardRef"
    type="button"
    class="group relative flex flex-col overflow-hidden rounded-2xl border bg-transparent text-left shadow-sm will-change-transform"
    :class="[
      selected
        ? 'border-primary shadow-md ring-2 ring-primary/30'
        : 'border-border hover:border-primary/40 hover:shadow-sm',
      isInteractionLocked ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
    ]"
    :style="tiltStyle"
    :aria-pressed="selected"
    :aria-label="`Select ${character.display_name}`"
    :disabled="isInteractionLocked"
    @click="onClick"
    @mouseenter="onMouseEnter"
    @mousemove="onMouseMove"
    @mouseleave="onMouseLeave"
  >
    <div class="relative h-[180px] overflow-hidden bg-transparent">
      <div
        class="absolute inset-0 z-0 will-change-transform"
        :style="bgParallaxStyle"
        aria-hidden="true"
      >
        <div
          class="absolute inset-0 bg-cover bg-center will-change-transform"
          :style="bgZoomStyle"
        />
      </div>
      <div
        class="absolute inset-0 z-[1] bg-gradient-to-t from-black/25 via-transparent to-transparent"
        aria-hidden="true"
      />
      <img
        :src="partnerThumbUrl(character.id)"
        :alt="character.display_name"
        class="absolute inset-0 z-10 h-full w-full object-contain object-bottom will-change-transform"
        :style="fgStyle"
        @error="onThumbError"
      />
      <span
        v-if="selected"
        class="absolute right-2.5 top-2.5 z-20 flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground shadow"
        aria-hidden="true"
      >
        <Check class="h-4 w-4" />
      </span>
    </div>
    <div class="relative space-y-2 border-t border-border/60 px-3 py-3">
      <div>
        <div class="truncate text-sm font-semibold text-foreground">{{ character.display_name }}</div>
        <div class="truncate text-xs text-muted-foreground">{{ character.persona_name }}</div>
      </div>
      <div class="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground">
        <AudioLines class="mt-0.5 h-3 w-3 shrink-0 text-primary/70" />
        <span class="line-clamp-2">Speaking style: {{ character.voice_preset_name }}</span>
      </div>
    </div>
  </button>
</template>
