<script setup lang="ts">
import { PARTNER_THUMB_PLACEHOLDER, partnerThumbUrl } from '@/config/partnerThumbs'
import type { AgentCharacter } from '@/services/conversationService'
import { AudioLines, Check } from 'lucide-vue-next'

const props = defineProps<{
  character: AgentCharacter
  selected: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

function onThumbError(event: Event) {
  const img = event.target as HTMLImageElement
  if (img.src.endsWith(PARTNER_THUMB_PLACEHOLDER)) return
  img.src = PARTNER_THUMB_PLACEHOLDER
}

function onClick() {
  if (props.disabled && !props.selected) return
  emit('toggle')
}
</script>

<template>
  <button
    type="button"
    class="group relative flex flex-col overflow-hidden rounded-2xl border bg-card/80 text-left shadow-sm backdrop-blur-md transition-all"
    :class="[
      selected
        ? 'border-primary shadow-md ring-2 ring-primary/30'
        : 'border-border hover:border-primary/40 hover:shadow-sm',
      disabled && !selected ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
    ]"
    :aria-pressed="selected"
    :aria-label="`Select ${character.display_name}`"
    :disabled="disabled && !selected"
    @click="onClick"
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
