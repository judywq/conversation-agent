<script setup lang="ts">
import { PROFILE_AVATARS, type ProfileAvatarId } from '@/config/profileAvatars'

const model = defineModel<string>({ default: '' })

function select(id: ProfileAvatarId) {
  model.value = id
}
</script>

<template>
  <div class="space-y-2">
    <div class="text-sm font-medium">Choose an avatar</div>
    <div class="flex flex-wrap gap-3">
      <button
        v-for="avatar in PROFILE_AVATARS"
        :key="avatar.id"
        type="button"
        class="relative h-14 w-14 overflow-hidden rounded-full border-2 transition-all"
        :class="
          model === avatar.id
            ? 'border-primary ring-2 ring-primary/30'
            : 'border-border hover:border-primary/40'
        "
        :aria-label="avatar.label"
        :aria-pressed="model === avatar.id"
        @click="select(avatar.id)"
      >
        <img :src="avatar.url" :alt="avatar.label" class="h-full w-full object-cover" />
      </button>
    </div>
  </div>
</template>
