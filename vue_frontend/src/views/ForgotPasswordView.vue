<template>
  <Card class="mx-auto w-full rounded-2xl border-border/80 shadow-lg shadow-primary/5 sm:w-[26rem]">
    <CardHeader>
      <CardTitle class="text-2xl font-bold">Forgot Password</CardTitle>
      <CardDescription>
        Enter your email address and we'll send you a link to reset your password
      </CardDescription>
    </CardHeader>
    <CardContent>
      <form @submit="handleSubmit" class="grid gap-4">
        <FormField
          v-slot="{ componentField }"
          name="email"
        >
          <FormItem>
            <FormLabel>Email</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="email"
                placeholder="name@example.com"
                :disabled="isSubmitting"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <div v-if="generalError" class="text-center text-sm text-destructive">
          {{ generalError }}
        </div>

        <Button
          type="submit"
          class="h-11 w-full font-semibold"
          :disabled="isSubmitting || !form.meta.value.valid"
        >
          {{ isSubmitting ? 'Sending...' : 'Send Reset Link' }}
        </Button>

        <div class="mt-2 text-center text-sm text-muted-foreground">
          Remember your password?
          <router-link
            :to="{ name: 'login' }"
            class="font-semibold text-primary hover:text-primary/80"
            :tabindex="isSubmitting ? -1 : 0"
          >
            Back to login
          </router-link>
        </div>
      </form>
    </CardContent>
  </Card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { AuthService } from '@/services/authService'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { forgotPasswordFormSchema } from '@/lib/validations'

const router = useRouter()
const isSubmitting = ref(false)
const generalError = ref<string | null>(null)

const form = useForm({
  validationSchema: toTypedSchema(forgotPasswordFormSchema),
  initialValues: {
    email: '',
  },
})

const handleSubmit = form.handleSubmit(async (values) => {
  isSubmitting.value = true
  generalError.value = null

  try {
    await AuthService.passwordReset(values.email)
    router.push({ name: 'password-reset-sent' })
  } catch (err: any) {
    if (err.fieldErrors) {
      form.setErrors(err.fieldErrors)
    }
    if (err.nonFieldError) {
      generalError.value = err.nonFieldError
    }
  } finally {
    isSubmitting.value = false
  }
})
</script>
