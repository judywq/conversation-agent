<script setup lang="ts">
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import HistorySessionList from '@/components/history/HistorySessionList.vue'
</script>

<template>
  <div class="container mx-auto py-8 px-4">
    <Card class="w-full mx-auto sm:max-w-4xl">
      <CardHeader>
        <CardTitle class="text-2xl">History</CardTitle>
        <CardDescription>
          Browse past discussions. Expand a chat to view the transcript, replay audio, and argument structure.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <HistorySessionList />
      </CardContent>
    </Card>
  </div>
</template>
