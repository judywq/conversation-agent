<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import AgentAvatarPanel from '@/components/conversation/AgentAvatarPanel.vue'
import SakuraMark from '@/components/SakuraMark.vue'
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
  live2d_url?: string | null
  character_id?: string
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

/** Shared cursor-anchored character menu. */
const menuOpen = ref(false)
const menuAgentId = ref<string | null>(null)
const menuPos = ref({ x: 0, y: 0 })

const menuAgent = computed(() => agents.value.find((a) => a.id === menuAgentId.value) ?? null)

async function openCharacterMenu(agent: AgentParticipant, event: MouseEvent) {
  menuAgentId.value = agent.id
  menuPos.value = { x: event.clientX + 4, y: event.clientY + 4 }
  // Close first if already open so radix remeasures against the new anchor.
  if (menuOpen.value) {
    menuOpen.value = false
    await nextTick()
  }
  menuOpen.value = true
}

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
      :live2d-url="agent.live2d_url || undefined"
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
    <!-- Interaction layer: gapless full-height columns so slot centers match the
         canvas layout math (i + 0.5) / n and the click target covers the character. -->
    <div class="flex h-full items-end justify-center">
      <div
        v-for="agent in agents"
        :key="agent.id"
        class="relative h-full flex-1"
      >
        <button
          type="button"
          class="absolute inset-0 z-[5] cursor-pointer"
          :aria-label="`${agent.name} options`"
          @click="openCharacterMenu(agent, $event)"
        />
      </div>
    </div>
    <!-- Cursor-anchored menu: invisible fixed trigger at the click point. -->
    <DropdownMenu v-model:open="menuOpen">
      <DropdownMenuTrigger
        class="pointer-events-none fixed z-[70] h-0 w-0 overflow-hidden opacity-0"
        :style="{ left: `${menuPos.x}px`, top: `${menuPos.y}px` }"
        tabindex="-1"
        aria-hidden="true"
      />
      <!-- z-[70]: the game overlay sits at z-[60], above the default portal z-50 -->
      <DropdownMenuContent v-if="menuAgent" align="start" side="bottom" class="z-[70]">
        <DropdownMenuItem
          v-if="replayingAgentId === menuAgent.id"
          @click="emit('stopReplay')"
        >
          Stop replay
        </DropdownMenuItem>
        <DropdownMenuItem
          v-else
          :disabled="!(replayableAgentIds ?? []).includes(menuAgent.id)"
          @click="emit('replay', menuAgent.id)"
        >
          Replay {{ menuAgent.name }}&rsquo;s last turn
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <!-- Dialog bar (visual-novel style): one half-transparent bar across the lower
         stage so it never covers a character's face. bottom-32 clears the mic cluster
         (the stage now reaches the viewport bottom). -->
    <div
      v-if="bubbleText"
      class="pointer-events-none absolute inset-x-0 bottom-32 z-10 flex justify-center px-4"
    >
      <!-- pointer-events-auto: the card must catch wheel/drag so overflow-y-auto is scrollable -->
      <div
        class="pointer-events-auto relative max-h-48 w-[min(56rem,92vw)] overflow-visible rounded-2xl border border-primary/15 bg-white/60 px-6 py-5 pr-14 text-lg text-foreground shadow-xl backdrop-blur-md sakura-petals"
      >
        <div
          class="absolute -top-3 left-5 inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground shadow"
        >
          <SakuraMark :size="14" class="text-primary-foreground" />
          {{ bubbleAgentName }}
        </div>
        <button
          type="button"
          class="absolute right-3 top-3 rounded-md border border-foreground/15 bg-white/80 px-2.5 py-1 text-sm font-medium text-foreground shadow-sm backdrop-blur transition-colors hover:bg-white"
          @click="emit('stopReplay')"
        >
          Stop
        </button>
        <div class="mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap leading-relaxed">
          {{ bubbleText }}
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
        :live2d-url="agent.live2d_url || undefined"
        :index="index"
        :active="activeSpeakerId === agent.id"
        :agent-status="agentStatus"
        :warmed-up="warmedUp"
      />
    </div>
  </div>
</template>
