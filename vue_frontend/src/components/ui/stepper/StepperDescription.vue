<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { StepperDescription } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <StepperDescription
    v-slot="slotProps"
    v-bind="$attrs"
    :class="cn('text-xs text-muted-foreground', props.class)"
  >
    <slot v-bind="slotProps" />
  </StepperDescription>
</template>
