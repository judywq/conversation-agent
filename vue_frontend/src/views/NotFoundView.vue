<template>
  <div class="container mx-auto max-w-md px-4 py-20 text-center">
    <SakuraMark :size="40" class="mx-auto mb-4" />
    <h1 class="mb-3 text-4xl font-bold">404</h1>
    <p class="mb-8 text-xl text-muted-foreground">Page not found</p>
    <router-link :to="{ name: 'home' }">
      <Button class="h-11 rounded-xl px-6 font-semibold">Return Home</Button>
    </router-link>
  </div>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SakuraMark from '@/components/SakuraMark.vue'
</script>
