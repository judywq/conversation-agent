<script setup lang="ts">
withDefaults(
  defineProps<{
    class?: string
    size?: number
  }>(),
  { size: 20 },
)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="currentColor"
    xmlns="http://www.w3.org/2000/svg"
    :class="['shrink-0 text-primary', $props.class]"
    aria-hidden="true"
  >
    <!-- Five soft petals around a center -->
    <ellipse cx="12" cy="6.2" rx="3.2" ry="4.2" />
    <ellipse cx="12" cy="6.2" rx="3.2" ry="4.2" transform="rotate(72 12 12)" />
    <ellipse cx="12" cy="6.2" rx="3.2" ry="4.2" transform="rotate(144 12 12)" />
    <ellipse cx="12" cy="6.2" rx="3.2" ry="4.2" transform="rotate(216 12 12)" />
    <ellipse cx="12" cy="6.2" rx="3.2" ry="4.2" transform="rotate(288 12 12)" />
    <circle cx="12" cy="12" r="2.4" class="text-primary-foreground" fill="hsl(var(--primary-foreground))" />
    <circle cx="12" cy="12" r="1.2" />
  </svg>
</template>
