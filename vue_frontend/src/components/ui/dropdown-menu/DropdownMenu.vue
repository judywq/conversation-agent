<script setup lang="ts">
import { DropdownMenuRoot, type DropdownMenuRootEmits, type DropdownMenuRootProps, useForwardPropsEmits } from 'radix-vue'

const props = withDefaults(defineProps<DropdownMenuRootProps>(), {
  // Avoid locking document body scroll when the menu opens (reka-ui#1670).
  modal: false,
})
const emits = defineEmits<DropdownMenuRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DropdownMenuRoot v-bind="forwarded">
    <slot />
  </DropdownMenuRoot>
</template>
