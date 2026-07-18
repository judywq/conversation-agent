<template>
  <Card class="mx-auto w-full rounded-2xl border-border/80 shadow-lg shadow-primary/5 sm:w-[26rem]">
    <CardHeader>
      <CardTitle class="text-2xl font-bold">Password Reset Sent</CardTitle>
      <CardDescription>
        Please check your email for a link to reset your password.
      </CardDescription>
    </CardHeader>
    <CardContent>
      <div class="grid gap-4">
        <router-link :to="{ name: 'login' }">
          <Button class="h-11 w-full font-semibold">Back to Login</Button>
        </router-link>
      </div>
    </CardContent>
  </Card>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
</script>
