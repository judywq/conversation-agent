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

type CharacterSettings = { zoom: number; offsetX: number; offsetY: number }

type SettingsFile = {
  version: 1
  global: {
    columns: number
    globalZoom: number
    stageWidth: number
    stageHeight: number
    snapshotRatio: number
    snapshotDelaySec: number
    lookAtCursor: boolean
  }
  characters: Record<string, CharacterSettings>
}

const cardsByUrl = ref(new Map<string, CardInstance>())
const loadingAll = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)
/** Preview multiplier; seed from config. Copy into AVATAR_GLOBAL_ZOOM when happy. */
const globalZoom = ref(AVATAR_GLOBAL_ZOOM)
/** Shared Live2D stage CSS size — controls framing / aspect for preview + photo. */
const stageWidth = ref(300)
const stageHeight = ref(400)
/** Multiplier on stage CSS size for Take photo (1 = Stage W×H pixels). */
const snapshotRatio = ref(1)
/** Delay before capture (seconds). */
const snapshotDelaySec = ref(0)
/** When true, models track the mouse cursor (engine autoFocus). */
const lookAtCursor = ref(true)
/** Cards per row (1–10). */
const columns = ref(5)

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${columns.value}, minmax(0, 1fr))`,
}))

function setCardRef(url: string, el: Element | ComponentPublicInstance | null) {
  if (el) {
    cardsByUrl.value.set(url, el as CardInstance)
  } else {
    cardsByUrl.value.delete(url)
  }
}

async function loadAll() {
  loadingAll.value = true
  try {
    await Promise.all([...cardsByUrl.value.values()].map((card) => card.load()))
  } finally {
    loadingAll.value = false
  }
}

function exportSettings() {
  const characters: Record<string, CharacterSettings> = {}
  for (const card of cardsByUrl.value.values()) {
    const { url, zoom, offsetX, offsetY } = card.getSettings()
    characters[url] = { zoom, offsetX, offsetY }
  }

  const payload: SettingsFile = {
    version: 1,
    global: {
      columns: columns.value,
      globalZoom: globalZoom.value,
      stageWidth: stageWidth.value,
      stageHeight: stageHeight.value,
      snapshotRatio: snapshotRatio.value,
      snapshotDelaySec: snapshotDelaySec.value,
      lookAtCursor: lookAtCursor.value,
    },
    characters,
  }

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = 'avatar-debug-settings.json'
  a.click()
  URL.revokeObjectURL(href)
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

function validateSettings(data: unknown): SettingsFile | null {
  if (!data || typeof data !== 'object') return null
  const root = data as Record<string, unknown>
  if (root.version !== 1) return null
  if (!root.global || typeof root.global !== 'object') return null
  if (!root.characters || typeof root.characters !== 'object') return null

  const g = root.global as Record<string, unknown>
  if (
    !isFiniteNumber(g.columns) ||
    !isFiniteNumber(g.globalZoom) ||
    !isFiniteNumber(g.stageWidth) ||
    !isFiniteNumber(g.stageHeight) ||
    !isFiniteNumber(g.snapshotRatio) ||
    !isFiniteNumber(g.snapshotDelaySec) ||
    typeof g.lookAtCursor !== 'boolean'
  ) {
    return null
  }

  const characters: Record<string, CharacterSettings> = {}
  for (const [url, raw] of Object.entries(root.characters as Record<string, unknown>)) {
    if (!raw || typeof raw !== 'object') return null
    const c = raw as Record<string, unknown>
    if (!isFiniteNumber(c.zoom) || !isFiniteNumber(c.offsetX) || !isFiniteNumber(c.offsetY)) {
      return null
    }
    characters[url] = { zoom: c.zoom, offsetX: c.offsetX, offsetY: c.offsetY }
  }

  return {
    version: 1,
    global: {
      columns: g.columns,
      globalZoom: g.globalZoom,
      stageWidth: g.stageWidth,
      stageHeight: g.stageHeight,
      snapshotRatio: g.snapshotRatio,
      snapshotDelaySec: g.snapshotDelaySec,
      lookAtCursor: g.lookAtCursor,
    },
    characters,
  }
}

function applyImportedSettings(settings: SettingsFile) {
  columns.value = settings.global.columns
  globalZoom.value = settings.global.globalZoom
  stageWidth.value = settings.global.stageWidth
  stageHeight.value = settings.global.stageHeight
  snapshotRatio.value = settings.global.snapshotRatio
  snapshotDelaySec.value = settings.global.snapshotDelaySec
  lookAtCursor.value = settings.global.lookAtCursor

  for (const [url, character] of Object.entries(settings.characters)) {
    const card = cardsByUrl.value.get(url)
    if (card) card.applySettings(character)
  }
}

function openImportPicker() {
  importInputRef.value?.click()
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  try {
    const text = await file.text()
    const parsed: unknown = JSON.parse(text)
    const settings = validateSettings(parsed)
    if (!settings) {
      console.error('Invalid avatar debug settings JSON', parsed)
      return
    }
    applyImportedSettings(settings)
  } catch (err) {
    console.error('Failed to import avatar debug settings', err)
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
      <div class="flex flex-wrap items-center gap-2">
        <Button variant="outline" @click="exportSettings">Export settings</Button>
        <Button variant="outline" @click="openImportPicker">Import settings</Button>
        <input
          ref="importInputRef"
          type="file"
          accept="application/json,.json"
          class="hidden"
          @change="onImportFile"
        />
        <Button :disabled="loadingAll" @click="loadAll">
          {{ loadingAll ? 'Loading…' : 'Load all avatars' }}
        </Button>
      </div>
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
      <span class="mx-1 hidden h-6 w-px bg-border sm:inline-block" aria-hidden="true" />
      <label class="flex cursor-pointer items-center gap-2 text-sm font-medium">
        <input
          v-model="lookAtCursor"
          type="checkbox"
          class="h-4 w-4 accent-primary"
          aria-label="Look at cursor"
        />
        Look at cursor
      </label>
    </div>

    <section class="space-y-3">
      <h2 class="text-lg font-medium">Female presets ({{ FEMALE_AVATAR_PRESETS.length }})</h2>
      <div class="grid gap-4" :style="gridStyle">
        <AvatarDebugCard
          v-for="preset in FEMALE_AVATAR_PRESETS"
          :key="`F-${preset.url}`"
          :ref="(el) => setCardRef(preset.url, el)"
          :preset="preset"
          :global-zoom="globalZoom"
          :stage-width="stageWidth"
          :stage-height="stageHeight"
          :snapshot-ratio="snapshotRatio"
          :snapshot-delay-sec="snapshotDelaySec"
          :look-at-cursor="lookAtCursor"
        />
      </div>
    </section>

    <section class="space-y-3">
      <h2 class="text-lg font-medium">Male presets ({{ MALE_AVATAR_PRESETS.length }})</h2>
      <div class="grid gap-4" :style="gridStyle">
        <AvatarDebugCard
          v-for="preset in MALE_AVATAR_PRESETS"
          :key="`M-${preset.url}`"
          :ref="(el) => setCardRef(preset.url, el)"
          :preset="preset"
          :global-zoom="globalZoom"
          :stage-width="stageWidth"
          :stage-height="stageHeight"
          :snapshot-ratio="snapshotRatio"
          :snapshot-delay-sec="snapshotDelaySec"
          :look-at-cursor="lookAtCursor"
        />
      </div>
    </section>
  </div>
</template>
