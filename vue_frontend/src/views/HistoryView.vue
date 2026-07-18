<script setup lang="ts">
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import HistorySessionList from '@/components/history/HistorySessionList.vue'
</script>

<template>
  <div class="container mx-auto px-4 py-8">
    <Card class="mx-auto w-full rounded-2xl border-border/80 shadow-sm sm:max-w-4xl">
      <CardHeader>
        <CardTitle class="text-2xl font-bold">History</CardTitle>
        <CardDescription>
          Browse past discussions. Expand a chat to view the transcript, replay audio, and speaker opinions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <HistorySessionList />
      </CardContent>
    </Card>
  </div>
</template>
