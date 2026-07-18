<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { StepperIndicator } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <StepperIndicator
    v-slot="slotProps"
    v-bind="$attrs"
    :class="
      cn(
        'inline-flex items-center justify-center rounded-full text-muted-foreground/50 w-8 h-8',
        'group-data-[disabled]:text-muted-foreground group-data-[disabled]:opacity-50',
        'group-data-[state=active]:bg-primary group-data-[state=active]:text-primary-foreground',
        'group-data-[state=completed]:bg-accent group-data-[state=completed]:text-accent-foreground',
        props.class,
      )
    "
  >
    <slot v-bind="slotProps" />
  </StepperIndicator>
</template>
