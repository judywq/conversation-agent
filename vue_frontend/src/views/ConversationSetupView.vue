<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useStorage } from '@vueuse/core'
import { BookOpen, Check, FolderOpen } from 'lucide-vue-next'
import PartnerSelectPanel from '@/components/conversation/PartnerSelectPanel.vue'
import SakuraCorner from '@/components/SakuraCorner.vue'
import SakuraMark from '@/components/SakuraMark.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/toast/use-toast'
import {
  ConversationService,
  type AgentCharacter,
  type DiscussionScenarioResult,
  type NewsCategory,
} from '@/services/conversationService'
import { ConversationWsClient, type ConversationWsEvent } from '@/services/conversationWs'
import { useAuthStore } from '@/stores/auth'
import { hideAppNav } from '@/composables/useLayoutChrome'
import { SCENE_OPTIONS, type SceneId, randomSceneId } from '@/lib/conversationScenes'

const { toast } = useToast()
const authStore = useAuthStore()
const router = useRouter()

const ws = new ConversationWsClient()
const connected = ref(false)
const topic = ref('')
const taxonomy = ref<NewsCategory[]>([])
const selectedCategory = ref('')
const selectedSubtopic = ref('')
const isGeneratingScenario = ref(false)
const scenarioArticles = ref<DiscussionScenarioResult['articles']>([])
const MAX_AGENT_COUNT = 3
const selectedCharacterIds = ref<string[]>([])
const characterRoster = ref<AgentCharacter[]>([])
const isStarting = ref(false)

const sceneId = useStorage<SceneId>('conv-game-scene', randomSceneId())

const canStart = computed(
  () =>
    connected.value &&
    !isStarting.value &&
    !!topic.value.trim() &&
    selectedCharacterIds.value.length >= 1 &&
    selectedCharacterIds.value.length <= MAX_AGENT_COUNT &&
    !!authStore.user?.profile_completed,
)

const availableSubtopics = computed(() => {
  const category = taxonomy.value.find((item) => item.slug === selectedCategory.value)
  return category?.subtopics ?? []
})

const canGenerateScenario = computed(
  () => !!selectedCategory.value && !!selectedSubtopic.value && !isGeneratingScenario.value,
)

watch(selectedCategory, () => {
  selectedSubtopic.value = ''
})

function handleEvent(e: ConversationWsEvent) {
  if (e.type === 'connected') {
    connected.value = true
  }
  if (e.type === 'session_started') {
    isStarting.value = false
    void router.replace({ name: 'conversation-session', params: { id: e.session_id } })
  }
  if (e.type === 'error') {
    isStarting.value = false
    toast({ title: 'Error', description: e.message, variant: 'destructive' })
  }
}

function startSession() {
  if (!authStore.user?.profile_completed || isStarting.value) return
  isStarting.value = true
  void (async () => {
    try {
      await ws.ready()
      const rosterById = new Map(characterRoster.value.map((c) => [c.id, c]))
      const character_personas: Record<string, string> = {}
      for (const id of selectedCharacterIds.value) {
        const persona = rosterById.get(id)?.persona_name
        if (persona) character_personas[id] = persona
      }
      ws.send({
        type: 'start_session',
        topic: topic.value.trim(),
        character_ids: selectedCharacterIds.value,
        character_personas,
      })
    } catch {
      isStarting.value = false
      connected.value = false
      toast({
        title: 'Connection error',
        description:
          'Could not connect to the conversation server. Please wait a moment and try again.',
        variant: 'destructive',
      })
    }
  })()
}

async function loadTaxonomy() {
  try {
    const payload = await ConversationService.fetchNewsTaxonomy()
    taxonomy.value = payload.categories
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Please refresh and try again.'
    toast({
      title: 'Could not load topics',
      description: message,
      variant: 'destructive',
    })
  }
}

async function generateDiscussionScenario() {
  if (!canGenerateScenario.value) return
  isGeneratingScenario.value = true
  try {
    const result = await ConversationService.generateDiscussionScenario(
      selectedCategory.value,
      selectedSubtopic.value,
    )
    topic.value = result.scenario
    scenarioArticles.value = result.articles ?? []
    await authStore.fetchUser()
    toast({
      title: 'Scenario ready',
      description: 'You can edit the text below before you start.',
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Please try again.'
    toast({
      title: 'Could not generate scenario',
      description: message,
      variant: 'destructive',
    })
  } finally {
    isGeneratingScenario.value = false
  }
}

onMounted(async () => {
  hideAppNav.value = false
  ws.connect()
  const off = ws.onEvent(handleEvent)
  const offConnection = ws.onConnectionChange((open) => {
    connected.value = open
  })
  onUnmounted(() => {
    off()
    offConnection()
  })
  await loadTaxonomy()
  try {
    await authStore.fetchUser()
    selectedCategory.value = authStore.user?.discussion_category?.trim() || ''
    selectedSubtopic.value = authStore.user?.discussion_subtopic?.trim() || ''
    const scenario = authStore.user?.discussion_scenario?.trim()
    if (scenario && !topic.value.trim()) {
      topic.value = scenario
    }
  } catch {
    // Keep the page usable if profile refresh fails.
  }
})

onUnmounted(() => {
  connected.value = false
  ws.close()
})
</script>

<template>
  <div class="container mx-auto space-y-6 px-4 py-8">
    <Card class="relative mx-auto max-w-5xl overflow-hidden rounded-2xl border-border/80 shadow-sm">
      <SakuraCorner class="opacity-80" :size="96" />
      <CardHeader class="relative z-[2] space-y-1">
        <CardTitle class="text-2xl font-bold">Discussion Setup</CardTitle>
        <CardDescription>
          Choose a topic, set the scene, then pick classmates for your seminar.
        </CardDescription>
      </CardHeader>
      <CardContent class="relative z-[2] space-y-6">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <div class="flex items-center gap-2 text-sm font-medium">
              <FolderOpen class="h-4 w-4 text-tag-foreground" />
              Major category
            </div>
            <Select v-model="selectedCategory" :disabled="isGeneratingScenario || isStarting">
              <SelectTrigger class="w-full">
                <SelectValue placeholder="Select a category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="category in taxonomy" :key="category.slug" :value="category.slug">
                  {{ category.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p class="text-xs text-muted-foreground">
              Choose the general subject you want to discuss today.
            </p>
          </div>
          <div class="space-y-2">
            <div class="flex items-center gap-2 text-sm font-medium">
              <BookOpen class="h-4 w-4 text-tag-foreground" />
              Subtopic
            </div>
            <Select
              v-model="selectedSubtopic"
              :disabled="!selectedCategory || isGeneratingScenario || isStarting"
            >
              <SelectTrigger class="w-full">
                <SelectValue placeholder="Select a subtopic" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="subtopic in availableSubtopics"
                  :key="subtopic.slug"
                  :value="subtopic.slug"
                >
                  {{ subtopic.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p class="text-xs text-muted-foreground">
              Pick a specific focus within that subject.
            </p>
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-sm font-medium">Discussion scenario</div>
            <Button
              variant="default"
              size="sm"
              class="font-semibold"
              :disabled="!canGenerateScenario"
              @click="generateDiscussionScenario"
            >
              <SakuraMark :size="14" class="text-primary-foreground" />
              {{ isGeneratingScenario ? 'Generating…' : 'Generate prompt' }}
            </Button>
          </div>
          <p v-if="isGeneratingScenario" class="text-sm text-muted-foreground">
            Preparing your scenario…
          </p>
          <p v-else-if="topic.trim() && scenarioArticles.length" class="text-sm text-muted-foreground">
            Scenario ready—you can edit it below before you start.
          </p>
          <Textarea
            v-model="topic"
            placeholder="Enter what you would like to discuss…"
            class="min-h-[100px] rounded-2xl"
            :disabled="isStarting"
          />
        </div>

        <div class="space-y-3">
          <div class="text-sm font-medium">Discussion environment</div>
          <div class="grid gap-3 sm:grid-cols-3">
            <button
              v-for="scene in SCENE_OPTIONS"
              :key="scene.id"
              type="button"
              class="group relative overflow-hidden rounded-2xl border text-left transition-all"
              :class="
                sceneId === scene.id
                  ? 'border-primary ring-2 ring-primary/30'
                  : 'border-border hover:border-primary/40'
              "
              :disabled="isStarting"
              @click="sceneId = scene.id"
            >
              <div
                class="h-24 bg-cover bg-center transition-transform duration-300 ease-out group-hover:scale-110"
                :class="sceneId === scene.id ? '' : 'grayscale opacity-60'"
                :style="{ backgroundImage: `url(${scene.thumbUrl})` }"
              />
              <div class="flex items-center justify-between gap-2 px-3 py-2">
                <span class="text-sm font-medium">{{ scene.label }}</span>
                <span
                  v-if="sceneId === scene.id"
                  class="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground"
                >
                  <Check class="h-3 w-3" />
                </span>
              </div>
            </button>
          </div>
        </div>

        <div class="space-y-3">
          <div class="space-y-1">
            <div class="text-sm font-medium">Choose Classmates</div>
            <p class="text-xs text-muted-foreground">
              Classmates who join you in the discussion.
            </p>
          </div>
          <PartnerSelectPanel
            v-model="selectedCharacterIds"
            :disabled="isStarting"
            @characters-loaded="characterRoster = $event"
          />
          <div class="pt-1">
            <Button
              class="h-11 px-8 text-base font-semibold"
              :disabled="!canStart"
              @click="startSession"
            >
              {{ isStarting ? 'Starting…' : 'Start discussion' }}
              <SakuraMark :size="16" class="text-primary-foreground" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
