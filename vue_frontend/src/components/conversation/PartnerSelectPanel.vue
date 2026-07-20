<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PartnerSelectCard from '@/components/conversation/PartnerSelectCard.vue'
import { Button } from '@/components/ui/button'
import { ConversationService, type AgentCharacter } from '@/services/conversationService'
import { Dices, Lightbulb, Loader2 } from 'lucide-vue-next'

const MAX_SELECTED = 3

const props = defineProps<{
  modelValue: string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [string[]]
}>()

const characters = ref<AgentCharacter[]>([])
const loading = ref(false)
const loadError = ref('')

const selectedSet = computed(() => new Set(props.modelValue))
const selectedCount = computed(() => props.modelValue.length)
const atMax = computed(() => selectedCount.value >= MAX_SELECTED)

onMounted(async () => {
  loading.value = true
  loadError.value = ''
  try {
    characters.value = await ConversationService.fetchAgentCharacters()
  } catch {
    loadError.value = 'Could not load partners. Refresh and try again.'
  } finally {
    loading.value = false
  }
})

function toggle(id: string) {
  if (props.disabled) return
  const current = [...props.modelValue]
  const index = current.indexOf(id)
  if (index >= 0) {
    current.splice(index, 1)
    emit('update:modelValue', current)
    return
  }
  if (current.length >= MAX_SELECTED) return
  current.push(id)
  emit('update:modelValue', current)
}

function randomSelect() {
  if (props.disabled || characters.value.length === 0) return
  const pool = [...characters.value]
  const k = 1 + Math.floor(Math.random() * Math.min(MAX_SELECTED, pool.length))
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j]!, pool[i]!]
  }
  emit(
    'update:modelValue',
    pool.slice(0, k).map((c) => c.id),
  )
}

function isCardDisabled(id: string) {
  return !!props.disabled || (atMax.value && !selectedSet.value.has(id))
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-sm text-muted-foreground">
        Select 1–{{ MAX_SELECTED }} classmates
      </p>
      <div class="flex items-center gap-2">
        <span
          class="rounded-full bg-accent px-3 py-1 text-xs font-semibold text-primary"
        >
          {{ selectedCount }} / {{ MAX_SELECTED }} selected
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="disabled || loading || characters.length === 0"
          @click="randomSelect"
        >
          <Dices class="mr-1.5 h-3.5 w-3.5" />
          Random
        </Button>
      </div>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 class="h-4 w-4 animate-spin" />
      Loading partners…
    </div>
    <p v-else-if="loadError" class="text-sm text-destructive">{{ loadError }}</p>
    <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <PartnerSelectCard
        v-for="(character, index) in characters"
        :key="character.id"
        :character="character"
        :background-index="index"
        :selected="selectedSet.has(character.id)"
        :disabled="isCardDisabled(character.id)"
        @toggle="toggle(character.id)"
      />
    </div>

    <div
      class="flex items-start gap-2.5 rounded-2xl border border-success/20 bg-success-muted px-4 py-3 text-sm text-success-muted-foreground"
    >
      <Lightbulb class="mt-0.5 h-4 w-4 shrink-0 text-success" />
      <p>
        Tip: Pick classmates with different speaking styles for a richer seminar discussion.
      </p>
    </div>
  </div>
</template>
