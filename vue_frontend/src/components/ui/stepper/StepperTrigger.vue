<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { StepperTrigger } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <StepperTrigger
    v-bind="$attrs"
    :class="cn('p-1 flex flex-col items-center text-center gap-1 rounded-md', props.class)"
  >
    <slot />
  </StepperTrigger>
</template>
