<script setup lang="ts">
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

const props = defineProps<{
  character: AgentCharacter
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

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const isInteractionLocked = computed(() => props.disabled && !props.selected)

const tiltStyle = computed(() => ({
  transform: `perspective(${TILT_PERSPECTIVE_PX}px) rotateX(${rotateX.value}deg) rotateY(${rotateY.value}deg) scale3d(${scale.value}, ${scale.value}, ${scale.value})`,
  transition: tilting.value
    ? 'box-shadow 150ms ease, border-color 150ms ease'
    : `transform ${TILT_RESET_MS}ms ease-out, box-shadow 150ms ease, border-color 150ms ease`,
}))

function resetTilt() {
  tilting.value = false
  rotateX.value = 0
  rotateY.value = 0
  scale.value = 1
}

function onMouseMove(event: MouseEvent) {
  if (isInteractionLocked.value || prefersReducedMotion()) return
  const el = cardRef.value
  if (!el) return

  tilting.value = true
  const rect = el.getBoundingClientRect()
  const x = (event.clientX - rect.left) / rect.width
  const y = (event.clientY - rect.top) / rect.height
  rotateY.value = (x - 0.5) * 2 * TILT_MAX_DEG
  rotateX.value = (0.5 - y) * 2 * TILT_MAX_DEG
  scale.value = TILT_SCALE
}

function onMouseLeave() {
  resetTilt()
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
    class="group relative flex flex-col overflow-hidden rounded-2xl border bg-card/80 text-left shadow-sm backdrop-blur-md will-change-transform"
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
    @mousemove="onMouseMove"
    @mouseleave="onMouseLeave"
  >
    <div class="relative h-[180px] bg-muted/40">
      <img
        :src="partnerThumbUrl(character.id)"
        :alt="character.display_name"
        class="absolute inset-0 z-0 h-full w-full object-contain object-bottom"
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
