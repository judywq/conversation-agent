<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { avatarPresetByUrl, resolveAvatarZoom } from '@/config/avatarPresets'
import { useLive2D } from '@/composables/useLive2D'
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

const stageRef = ref<HTMLElement | null>(null)
const { status, errorMessage, init, dispose } = useLive2D(stageRef)

async function load() {
  if (status.value === 'ready' || status.value === 'loading') return
  await nextTick()
  if (!stageRef.value) return
  const base = avatarPresetByUrl(props.character.live2d_url) ?? {
    url: props.character.live2d_url,
  }
  await init({
    ...base,
    zoom: resolveAvatarZoom(base.zoom),
  })
}

watch(
  () => props.character.live2d_url,
  () => {
    dispose()
    void load()
  },
)

onMounted(() => {
  void load()
})

onUnmounted(() => {
  dispose()
})

function onClick() {
  if (props.disabled && !props.selected) return
  emit('toggle')
}
</script>

<template>
  <button
    type="button"
    class="group relative flex flex-col overflow-hidden rounded-2xl border bg-card text-left transition-all"
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
      <div ref="stageRef" class="absolute inset-0 z-0" />
      <div
        v-if="status === 'idle' || status === 'loading'"
        class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-2 text-center text-xs text-muted-foreground"
      >
        Loading…
      </div>
      <div
        v-else-if="status === 'error'"
        class="absolute inset-0 z-10 flex items-center justify-center px-2 text-center text-xs text-destructive"
      >
        {{ errorMessage || 'Avatar unavailable' }}
      </div>
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
      <div>
        <span
          class="inline-block rounded-full border border-success/20 bg-success-muted px-2.5 py-0.5 text-[10px] font-medium text-success-muted-foreground"
        >
          {{ character.persona_name }}
        </span>
      </div>
      <div class="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground">
        <AudioLines class="mt-0.5 h-3 w-3 shrink-0 text-primary/70" />
        <span class="line-clamp-2">Speaking style: {{ character.voice_preset_name }}</span>
      </div>
    </div>
  </button>
</template>
