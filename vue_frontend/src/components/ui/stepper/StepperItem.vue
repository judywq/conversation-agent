<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { StepperItem } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
  step: number
}>()
</script>

<template>
  <StepperItem
    v-slot="slotProps"
    v-bind="$attrs"
    :step="props.step"
    :class="cn('flex items-center gap-2 group data-[disabled]:pointer-events-none', props.class)"
  >
    <slot v-bind="slotProps" />
  </StepperItem>
</template>
