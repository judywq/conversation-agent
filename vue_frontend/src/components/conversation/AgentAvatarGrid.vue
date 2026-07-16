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
  /** Game mode: stage-wide canvases (big, no clipping) vs boxed per-slot canvases. */
  fullStage?: boolean
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
    <!-- Full-stage canvas layer: each model gets a stage-wide canvas and is fitted
         to its slot column by useLive2D, so motions can overdraw without clipping. -->
    <template v-if="fullStage">
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
        :active="activeSpeakerId === agent.id"
        :agent-status="agentStatus"
        :warmed-up="warmedUp"
        class="absolute inset-0 transition-[filter]"
        :class="activeSpeakerId === agent.id ? 'drop-shadow-[0_0_24px_rgba(255,255,255,0.55)]' : ''"
      />
    </template>
    <!-- Interaction layer: hosts the click menu and bubble. Full-stage uses gapless
         full-width columns so slot centers match the canvas layout math (i + 0.5) / n;
         boxed renders the panel inside its slot (canvas-clipped, smaller characters). -->
    <div class="flex h-full items-end justify-center" :class="fullStage ? '' : 'gap-[4vw]'">
      <div
        v-for="(agent, index) in agents"
        :key="agent.id"
        class="relative h-[min(72vh,720px)] transition-[filter]"
        :class="[
          fullStage ? 'flex-1' : 'w-[min(30vw,420px)]',
          !fullStage && activeSpeakerId === agent.id
            ? 'drop-shadow-[0_0_24px_rgba(255,255,255,0.55)]'
            : '',
        ]"
      >
        <AgentAvatarPanel
          v-if="!fullStage"
          game
          :ref="(el) => setPanelRef(agent.id, el as InstanceType<typeof AgentAvatarPanel> | null)"
          :agent-id="agent.id"
          :name="agent.name"
          :gender="agent.avatar_body || agent.gender"
          :index="index"
          :active="activeSpeakerId === agent.id"
          :agent-status="agentStatus"
          :warmed-up="warmedUp"
          class="h-full"
        />
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
        <div
          v-if="bubbleText && bubbleAgentId === agent.id"
          class="pointer-events-none absolute -top-2 left-1/2 z-10 w-[min(24rem,70vw)] -translate-x-1/2 -translate-y-full"
        >
          <!-- pointer-events-auto: the card must catch wheel/drag so overflow-y-auto is scrollable -->
          <div class="pointer-events-auto max-h-40 overflow-y-auto rounded-2xl border bg-white/95 px-4 py-3 text-sm text-gray-900 shadow-lg">
            <div class="mb-0.5 font-semibold">{{ agent.name }}</div>
            <div class="whitespace-pre-wrap">{{ bubbleText }}</div>
          </div>
          <div class="mx-auto -mt-1.5 h-3 w-3 rotate-45 border-b border-r bg-white/95" />
        </div>
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
