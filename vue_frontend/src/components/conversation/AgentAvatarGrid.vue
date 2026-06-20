<script setup lang="ts">
import { computed, ref } from 'vue'
import AgentAvatarPanel from '@/components/conversation/AgentAvatarPanel.vue'
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
}>()

const panelRefs = ref<Record<string, InstanceType<typeof AgentAvatarPanel> | null>>({})

const agents = computed(() => props.participants.filter((p) => p.type === 'agent'))

const gridClass = computed(() => {
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
  <div class="space-y-3" aria-live="polite">
    <div class="text-sm font-medium">Agent avatars</div>
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
