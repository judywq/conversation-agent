<template>
  <div class="container mx-auto px-4 py-16 text-center sm:py-24">
    <div class="mx-auto flex max-w-xl flex-col items-center gap-5">
      <div class="flex items-center gap-2">
        <SakuraMark :size="36" />
        <span class="text-sm font-bold tracking-[0.2em] text-primary uppercase">ConvAgent</span>
      </div>
      <h1 class="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
        Campus conversations, reimagined
      </h1>
      <p class="text-lg text-muted-foreground">
        Practice academic dialogue with AI classmates in a visual-novel style seminar.
      </p>
      <router-link :to="{ name: 'login' }">
        <Button class="h-11 px-8 text-base font-semibold">
          Enter Campus
          <SakuraMark :size="16" class="text-primary-foreground" />
        </Button>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from '@/components/ui/button/Button.vue'
import SakuraMark from '@/components/SakuraMark.vue'
</script>
