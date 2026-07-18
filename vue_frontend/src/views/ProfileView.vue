<template>
  <div class="container mx-auto px-4 py-8">
    <Card class="mx-auto w-full rounded-2xl border-border/80 shadow-sm sm:max-w-3xl">
      <CardHeader class="space-y-3">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div class="space-y-1">
            <CardTitle class="text-2xl font-bold">My Profile</CardTitle>
            <CardDescription>
              {{
                authStore.user?.profile_completed
                  ? 'Review or update your language-learning profile.'
                  : 'Set up your language-learning profile before starting conversations.'
              }}
            </CardDescription>
          </div>
          <div
            class="inline-flex w-fit items-center rounded-full border px-3 py-1 text-xs font-medium"
            :class="
              authStore.user?.profile_completed
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                : 'border-amber-200 bg-amber-50 text-amber-800'
            "
          >
            {{ authStore.user?.profile_completed ? 'Profile complete' : 'Profile incomplete' }}
          </div>
        </div>
      </CardHeader>
      <CardContent class="space-y-6">
        <ProfileCompletedView v-if="authStore.user?.profile_completed" />
        <ProfileOnboardingWizard v-else />

        <Button
          v-if="authStore.user?.profile_completed"
          class="h-11 w-full rounded-xl"
          variant="default"
          @click="handleGoToConversation"
        >
          Go to Conversation
        </Button>
      </CardContent>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import ProfileCompletedView from '@/components/profile/ProfileCompletedView.vue'
import ProfileOnboardingWizard from '@/components/profile/ProfileOnboardingWizard.vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

async function handleGoToConversation() {
  await router.push({ name: 'conversation' })
}
</script>
