<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import {
  AVATAR_GLOBAL_ZOOM,
  FEMALE_AVATAR_PRESETS,
  MALE_AVATAR_PRESETS,
} from '@/config/avatarPresets'
import AvatarDebugCard from '@/components/conversation/AvatarDebugCard.vue'
import { Button } from '@/components/ui/button'

type CardInstance = InstanceType<typeof AvatarDebugCard>

const cards = ref<CardInstance[]>([])
const loadingAll = ref(false)
/** Preview multiplier; seed from config. Copy into AVATAR_GLOBAL_ZOOM when happy. */
const globalZoom = ref(AVATAR_GLOBAL_ZOOM)
/** Shared Live2D stage CSS size — controls framing / aspect for preview + photo. */
const stageWidth = ref(300)
const stageHeight = ref(400)
/** Multiplier on stage CSS size for Take photo (1 = Stage W×H pixels). */
const snapshotRatio = ref(1)
/** Delay before capture (seconds). */
const snapshotDelaySec = ref(1)
/** Cards per row (1–10). */
const columns = ref(5)

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${columns.value}, minmax(0, 1fr))`,
}))

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
  <div class="w-full space-y-6 px-4 py-6">
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

    <div class="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3">
      <span class="shrink-0 text-sm font-medium">Columns</span>
      <input
        v-model.number="columns"
        type="range"
        min="1"
        max="10"
        step="1"
        class="h-8 w-32 accent-primary"
        aria-label="Cards per row"
      />
      <code class="w-4 shrink-0 text-right font-mono text-sm tabular-nums">{{ columns }}</code>
      <span class="mx-1 hidden h-6 w-px bg-border sm:inline-block" aria-hidden="true" />
      <span class="shrink-0 text-sm font-medium">Global zoom</span>
      <input
        v-model.number="globalZoom"
        type="range"
        min="0.2"
        max="3"
        step="0.05"
        class="h-8 min-w-0 flex-1 accent-primary sm:max-w-md"
        aria-label="Global zoom"
      />
      <code
        class="w-12 shrink-0 select-all text-right font-mono text-sm tabular-nums"
        title="Copy into avatarPresets.ts as AVATAR_GLOBAL_ZOOM"
        >{{ globalZoom.toFixed(2) }}</code
      >
      <span class="mx-1 hidden h-6 w-px bg-border sm:inline-block" aria-hidden="true" />
      <span class="shrink-0 text-sm font-medium">Stage</span>
      <label class="flex items-center gap-1.5 text-sm text-muted-foreground">
        W
        <input
          v-model.number="stageWidth"
          type="number"
          min="120"
          max="1200"
          step="1"
          class="h-8 w-20 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
          aria-label="Stage width"
        />
      </label>
      <label class="flex items-center gap-1.5 text-sm text-muted-foreground">
        H
        <input
          v-model.number="stageHeight"
          type="number"
          min="120"
          max="1200"
          step="1"
          class="h-8 w-20 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
          aria-label="Stage height"
        />
      </label>
      <span class="mx-1 hidden h-6 w-px bg-border sm:inline-block" aria-hidden="true" />
      <span class="shrink-0 text-sm font-medium">Photo ratio</span>
      <input
        v-model.number="snapshotRatio"
        type="number"
        min="0.25"
        max="8"
        step="0.25"
        class="h-8 w-20 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
        aria-label="Snapshot scale ratio"
        title="Export size = Stage CSS × ratio (ignores display DPR)"
      />
      <span class="mx-1 hidden h-6 w-px bg-border sm:inline-block" aria-hidden="true" />
      <span class="shrink-0 text-sm font-medium">Photo delay</span>
      <label class="flex items-center gap-1.5 text-sm text-muted-foreground">
        <input
          v-model.number="snapshotDelaySec"
          type="number"
          min="0"
          max="10"
          step="0.5"
          class="h-8 w-16 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
          aria-label="Snapshot delay seconds"
        />
        s
      </label>
    </div>

    <section class="space-y-3">
      <h2 class="text-lg font-medium">Female presets ({{ FEMALE_AVATAR_PRESETS.length }})</h2>
      <div class="grid gap-4" :style="gridStyle">
        <AvatarDebugCard
          v-for="preset in FEMALE_AVATAR_PRESETS"
          :key="`F-${preset.url}`"
          :ref="setCardRef"
          :preset="preset"
          :global-zoom="globalZoom"
          :stage-width="stageWidth"
          :stage-height="stageHeight"
          :snapshot-ratio="snapshotRatio"
          :snapshot-delay-sec="snapshotDelaySec"
        />
      </div>
    </section>

    <section class="space-y-3">
      <h2 class="text-lg font-medium">Male presets ({{ MALE_AVATAR_PRESETS.length }})</h2>
      <div class="grid gap-4" :style="gridStyle">
        <AvatarDebugCard
          v-for="preset in MALE_AVATAR_PRESETS"
          :key="`M-${preset.url}`"
          :ref="setCardRef"
          :preset="preset"
          :global-zoom="globalZoom"
          :stage-width="stageWidth"
          :stage-height="stageHeight"
          :snapshot-ratio="snapshotRatio"
          :snapshot-delay-sec="snapshotDelaySec"
        />
      </div>
    </section>
  </div>
</template>
