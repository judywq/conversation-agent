<script setup lang="ts">
import { ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { FEMALE_AVATAR_PRESETS, MALE_AVATAR_PRESETS } from '@/config/avatarPresets'
import AvatarDebugCard from '@/components/conversation/AvatarDebugCard.vue'
import { Button } from '@/components/ui/button'

type CardInstance = InstanceType<typeof AvatarDebugCard>

const cards = ref<CardInstance[]>([])
const loadingAll = ref(false)

function setCardRef(el: Element | ComponentPublicInstance | null) {
  if (el) {
    cards.value.push(el as CardInstance)
  }
}

async function loadAll() {
  loadingAll.value = true
  try {
    await Promise.all(cards.value.map((card) => card.load()))
  } finally {
    loadingAll.value = false
  }
}
</script>

<template>
  <div class="container mx-auto max-w-6xl space-y-6 px-4 py-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold">Avatar debug</h1>
        <p class="text-sm text-muted-foreground">
          All presets from <code>src/config/avatarPresets.ts</code>. Load avatars individually or
          all at once.
        </p>
      </div>
      <Button :disabled="loadingAll" @click="loadAll">
        {{ loadingAll ? 'Loading…' : 'Load all avatars' }}
      </Button>
    </div>

    <section class="space-y-3">
      <h2 class="text-lg font-medium">Female presets ({{ FEMALE_AVATAR_PRESETS.length }})</h2>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <AvatarDebugCard
          v-for="preset in FEMALE_AVATAR_PRESETS"
          :key="`F-${preset.url}`"
          :ref="setCardRef"
          :preset="preset"
        />
      </div>
    </section>

    <section class="space-y-3">
      <h2 class="text-lg font-medium">Male presets ({{ MALE_AVATAR_PRESETS.length }})</h2>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <AvatarDebugCard
          v-for="preset in MALE_AVATAR_PRESETS"
          :key="`M-${preset.url}`"
          :ref="setCardRef"
          :preset="preset"
        />
      </div>
    </section>
  </div>
</template>
