<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { StepperSeparator } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <StepperSeparator
    v-bind="$attrs"
    :class="
      cn(
        'bg-muted',
        'group-data-[disabled]:bg-muted group-data-[disabled]:opacity-50',
        'group-data-[state=completed]:bg-accent',
        props.class,
      )
    "
  />
</template>
