<script setup lang="ts">
import { computed, ref } from 'vue'
import AgentAvatarPanel from '@/components/conversation/AgentAvatarPanel.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { LipSyncPayload } from '@/types/lipsync'

export type AgentParticipant = {
  id: string
  name: string
  type: 'user' | 'agent'
  persona_name?: string
  gender?: string
  voice_title?: string
  avatar_body?: string
}

const props = defineProps<{
  participants: AgentParticipant[]
  activeSpeakerId: string | null
  agentStatus: 'idle' | 'thinking' | 'finished' | 'searching_online'
  warmedUp: boolean
  /** When true, stack avatars in one column (better for the sidebar partner column). */
  stacked?: boolean
  /** Immersive game-phase rendering: characters side-by-side, bubble + click menu. */
  game?: boolean
  /** User size multiplier from the settings slider; default 1. */
  avatarScale?: number
  /** Utterance shown in a speech bubble over the active speaker (game mode only). */
  bubbleText?: string | null
  /** Agent the bubble anchors to — the bubble turn's speaker, not activeSpeakerId, so replays anchor correctly. */
  bubbleAgentId?: string | null
  /** Agents whose last turn can be replayed via the character click menu. */
  replayableAgentIds?: string[]
  /** Agent whose replay is currently playing (shows a Stop item instead). */
  replayingAgentId?: string | null
}>()

const emit = defineEmits<{
  replay: [agentId: string]
  stopReplay: []
}>()

const panelRefs = ref<Record<string, InstanceType<typeof AgentAvatarPanel> | null>>({})

const agents = computed(() => props.participants.filter((p) => p.type === 'agent'))

const bubbleAgentName = computed(
  () => agents.value.find((a) => a.id === props.bubbleAgentId)?.name ?? '',
)

const gridClass = computed(() => {
  if (props.stacked) return 'grid-cols-1'
  const count = agents.value.length
  if (count <= 1) return 'grid-cols-1'
  if (count <= 2) return 'grid-cols-1 sm:grid-cols-2'
  if (count <= 4) return 'grid-cols-1 sm:grid-cols-2'
  return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
})

function setPanelRef(agentId: string, el: InstanceType<typeof AgentAvatarPanel> | null) {
  if (el) {
    panelRefs.value[agentId] = el
  } else {
    delete panelRefs.value[agentId]
  }
}

async function speak(agentId: string, audioUrl: string, lipsync: LipSyncPayload): Promise<boolean> {
  const panel = panelRefs.value[agentId]
  if (!panel) return false
  return panel.speakTurn(audioUrl, lipsync)
}

function disposeAll() {
  for (const panel of Object.values(panelRefs.value)) {
    panel?.dispose()
  }
  panelRefs.value = {}
}

function setIdleAll() {
  for (const panel of Object.values(panelRefs.value)) {
    panel?.setIdle()
  }
}

async function ensureAllInitialized() {
  await Promise.all(
    Object.values(panelRefs.value).map((panel) => panel?.ensureInit?.() ?? Promise.resolve()),
  )
}

defineExpose({
  speak,
  disposeAll,
  ensureAllInitialized,
  setIdleAll,
})
</script>

<template>
  <div v-if="game" class="relative h-full" aria-live="polite">
    <!-- Canvas layer: each model gets a stage-wide canvas and is fitted to its slot
         column by useLive2D, so motions can overdraw without clipping. Panels are
         persistent (only zoom changes via the size slider) so in-flight speak()
         audio/lipsync survives a resize. -->
    <AgentAvatarPanel
      v-for="(agent, index) in agents"
      :key="agent.id"
      game
      :ref="(el) => setPanelRef(agent.id, el as InstanceType<typeof AgentAvatarPanel> | null)"
      :agent-id="agent.id"
      :name="agent.name"
      :gender="agent.avatar_body || agent.gender"
      :index="index"
      :slot-count="agents.length"
      :slot-index="index"
      :zoom-scale="avatarScale ?? 1"
      :active="activeSpeakerId === agent.id"
      :agent-status="agentStatus"
      :warmed-up="warmedUp"
      class="absolute inset-0 transition-[filter]"
      :class="activeSpeakerId === agent.id ? 'drop-shadow-[0_0_24px_rgba(255,255,255,0.55)]' : ''"
    />
    <!-- Interaction layer: hosts the click menu. Gapless full-height columns so
         slot centers match the canvas layout math (i + 0.5) / n and the click
         target covers the whole character, head included. -->
    <div class="flex h-full items-end justify-center">
      <div
        v-for="agent in agents"
        :key="agent.id"
        class="relative h-full flex-1"
      >
        <DropdownMenu>
          <DropdownMenuTrigger
            class="absolute inset-0 z-[5] cursor-pointer"
            :aria-label="`${agent.name} options`"
          />
          <!-- z-[70]: the game overlay sits at z-[60], above the default portal z-50 -->
          <DropdownMenuContent align="center" class="z-[70]">
            <DropdownMenuItem v-if="replayingAgentId === agent.id" @click="emit('stopReplay')">
              Stop replay
            </DropdownMenuItem>
            <DropdownMenuItem
              v-else
              :disabled="!(replayableAgentIds ?? []).includes(agent.id)"
              @click="emit('replay', agent.id)"
            >
              Replay {{ agent.name }}&rsquo;s last turn
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
    <!-- Dialog bar (visual-novel style): one half-transparent bar across the lower
         stage so it never covers a character's face. bottom-28 clears the mic cluster. -->
    <div
      v-if="bubbleText"
      class="pointer-events-none absolute inset-x-0 bottom-28 z-10 flex justify-center px-4"
    >
      <!-- pointer-events-auto: the card must catch wheel/drag so overflow-y-auto is scrollable -->
      <div
        class="pointer-events-auto max-h-48 w-[min(56rem,92vw)] overflow-y-auto rounded-2xl border border-white/40 bg-white/50 px-5 py-3 text-lg text-gray-900 shadow-lg backdrop-blur-sm"
      >
        <div class="mb-0.5 font-semibold">{{ bubbleAgentName }}</div>
        <div class="whitespace-pre-wrap">{{ bubbleText }}</div>
      </div>
    </div>
  </div>
  <div v-else class="space-y-3" aria-live="polite">
    <div class="text-sm font-medium">Discussion partners</div>
    <div class="grid gap-3" :class="gridClass">
      <AgentAvatarPanel
        v-for="(agent, index) in agents"
        :key="agent.id"
        :ref="(el) => setPanelRef(agent.id, el as InstanceType<typeof AgentAvatarPanel> | null)"
        :agent-id="agent.id"
        :name="agent.name"
        :gender="agent.avatar_body || agent.gender"
        :index="index"
        :active="activeSpeakerId === agent.id"
        :agent-status="agentStatus"
        :warmed-up="warmedUp"
      />
    </div>
  </div>
</template>
