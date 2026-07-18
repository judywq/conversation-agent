<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { avatarPresetByUrl, resolveAvatarZoom } from '@/config/avatarPresets'
import { useLive2D } from '@/composables/useLive2D'
import type { AgentCharacter } from '@/services/conversationService'
import { Check } from 'lucide-vue-next'

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

const statusLabel = computed(() => {
  if (status.value === 'loading') return 'Loading…'
  if (status.value === 'error') return 'Unavailable'
  if (status.value === 'ready') return props.character.persona_name
  return 'Loading…'
})

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
    class="group relative flex flex-col overflow-hidden rounded-lg border bg-card text-left transition-shadow"
    :class="[
      selected
        ? 'border-primary shadow-md ring-1 ring-primary/40'
        : 'border-border hover:border-primary/40',
      disabled && !selected ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
    ]"
    :aria-pressed="selected"
    :aria-label="`Select ${character.display_name}`"
    :disabled="disabled && !selected"
    @click="onClick"
  >
    <div class="relative h-[160px] bg-muted/30">
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
        class="absolute right-2 top-2 z-20 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground"
        aria-hidden="true"
      >
        <Check class="h-3.5 w-3.5" />
      </span>
    </div>
    <div class="border-t px-3 py-2">
      <div class="truncate text-sm font-medium">{{ character.display_name }}</div>
      <div class="truncate text-xs text-muted-foreground">{{ statusLabel }}</div>
    </div>
  </button>
</template>
