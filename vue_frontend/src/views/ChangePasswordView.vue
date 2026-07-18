<template>
  <Card class="mx-auto w-full rounded-2xl border-border/80 shadow-lg shadow-primary/5 sm:w-[26rem]">
    <CardHeader>
      <CardTitle class="text-2xl font-bold">Change Password</CardTitle>
      <CardDescription>Enter your current password and a new password</CardDescription>
    </CardHeader>
    <CardContent>
      <div
        v-if="authStore.user?.must_change_password"
        class="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        role="alert"
      >
        Your account requires a new password before you can continue.
      </div>
      <form @submit="handleSubmit" class="grid gap-4">
        <FormField
          v-slot="{ componentField }"
          name="old_password"
        >
          <FormItem>
            <FormLabel>Current Password</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="password"
                placeholder="Enter your current password"
                class="h-11 rounded-xl"
                :disabled="isSubmitting || success"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField
          v-slot="{ componentField }"
          name="new_password1"
        >
          <FormItem>
            <FormLabel>New Password</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="password"
                placeholder="Enter your new password"
                class="h-11 rounded-xl"
                :disabled="isSubmitting || success"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField
          v-slot="{ componentField }"
          name="new_password2"
        >
          <FormItem>
            <FormLabel>Confirm New Password</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="password"
                placeholder="Confirm your new password"
                class="h-11 rounded-xl"
                :disabled="isSubmitting || success"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <div v-if="generalError" class="text-destructive text-sm text-center">
          {{ generalError }}
        </div>

        <Button
          type="submit"
          class="h-11 w-full rounded-xl font-semibold"
          :disabled="isSubmitting || !form.meta.value.valid || success"
        >
          {{ isSubmitting ? 'Changing...' : 'Change Password' }}
        </Button>

        <p v-if="success" class="text-center text-sm text-success">
          Password changed successfully! Redirecting...
        </p>
      </form>
    </CardContent>
  </Card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
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
import { useToast } from '@/components/ui/toast/use-toast'
import { changePasswordFormSchema } from '@/lib/validations'
import { defaultAuthenticatedRoute } from '@/lib/authNavigation'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const isSubmitting = ref(false)
const generalError = ref<string | null>(null)
const success = ref(false)
const { toast } = useToast()
const authStore = useAuthStore()
const router = useRouter()

const form = useForm({
  validationSchema: toTypedSchema(changePasswordFormSchema),
  initialValues: {
    old_password: '',
    new_password1: '',
    new_password2: '',
  },
})

const handleSubmit = form.handleSubmit(async (values) => {
  isSubmitting.value = true
  generalError.value = null

  try {
    await AuthService.changePassword(values.old_password, values.new_password1, values.new_password2)
    success.value = true
    authStore.setMustChangePasswordFalse()
    toast({
      title: 'Success',
      description: 'Your password has been changed successfully.',
    })
    setTimeout(() => {
      router.push(defaultAuthenticatedRoute())
    }, 3000)
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
