<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="
      cn(
        'rounded-lg border border-border/80 bg-card/40 text-card-foreground shadow-sm backdrop-blur-md',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>
