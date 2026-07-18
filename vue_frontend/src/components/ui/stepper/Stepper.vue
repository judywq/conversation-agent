<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { StepperRoot } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <StepperRoot
    v-slot="slotProps"
    v-bind="$attrs"
    :class="cn('flex gap-2', props.class)"
  >
    <slot v-bind="slotProps" />
  </StepperRoot>
</template>
