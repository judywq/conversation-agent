<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { LlmService, type LlmModel } from '@/services/llmService'

const authStore = useAuthStore()
const username = computed(() => authStore.user?.username ?? authStore.user?.email ?? 'User')

const loading = ref(false)
const error = ref<string | null>(null)
const models = ref<LlmModel[]>([])

async function loadModels() {
  loading.value = true
  error.value = null
  try {
    models.value = await LlmService.listActiveModels()
  } catch (e: any) {
    error.value = e?.message ?? 'Failed to load LLM models.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadModels()
})
</script>

<template>
  <div class="container mx-auto py-10 space-y-6">
    <Card>
      <CardHeader>
        <CardTitle>Dashboard</CardTitle>
        <CardDescription>Signed in as <span class="font-medium">{{ username }}</span>.</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="flex items-center justify-between gap-4">
          <div class="text-sm text-muted-foreground">
            This is a placeholder home for your new project. Add new features from here.
          </div>
          <Button variant="outline" :disabled="loading" @click="loadModels">
            {{ loading ? 'Refreshing…' : 'Refresh models' }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Active LLM models</CardTitle>
        <CardDescription>From <code>/api/llm/models/</code>.</CardDescription>
      </CardHeader>
      <CardContent>
        <div v-if="error" class="text-sm text-destructive mb-3">{{ error }}</div>
        <div v-if="loading && models.length === 0" class="text-sm text-muted-foreground">Loading…</div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="text-left border-b">
              <tr>
                <th class="py-2 pr-4">Display</th>
                <th class="py-2 pr-4">Name</th>
                <th class="py-2 pr-4">Provider</th>
                <th class="py-2 pr-4">Default</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in models" :key="m.id" class="border-b last:border-b-0">
                <td class="py-2 pr-4 font-medium">{{ m.display_name }}</td>
                <td class="py-2 pr-4 font-mono">{{ m.name }}</td>
                <td class="py-2 pr-4">{{ m.llm_type }}</td>
                <td class="py-2 pr-4">{{ m.is_default ? 'Yes' : 'No' }}</td>
              </tr>
              <tr v-if="!loading && models.length === 0">
                <td colspan="4" class="py-4 text-muted-foreground">No active models found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

