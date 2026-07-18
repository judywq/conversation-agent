<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import SakuraMark from '@/components/SakuraMark.vue'
import { Loader2 } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { signupFormSchema } from '@/lib/validations'

const authStore = useAuthStore()
const { loading } = storeToRefs(authStore)
const router = useRouter()
const generalError = ref<string | null>(null)

const form = useForm({
  validationSchema: toTypedSchema(signupFormSchema),
  initialValues: {
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
  },
})

const onSubmit = form.handleSubmit(async (values) => {
  try {
    generalError.value = null
    await authStore.signup(values.email, values.password, values.name, router)
  } catch (err: any) {
    if (err.fieldErrors) {
      form.setErrors(err.fieldErrors)
    }
    if (err.nonFieldError) {
      generalError.value = err.nonFieldError
    }
  }
})
</script>

<template>
  <Card class="mx-auto w-full overflow-hidden rounded-2xl border-border/80 shadow-lg shadow-primary/5 sm:w-[26rem]">
    <CardHeader class="space-y-2 text-center">
      <div class="flex items-center justify-center gap-2">
        <SakuraMark :size="24" />
        <span class="text-lg font-bold tracking-[0.14em] uppercase">ConvAgent</span>
      </div>
      <CardTitle class="text-2xl font-bold">Create an account</CardTitle>
      <CardDescription>Join the campus dialogue</CardDescription>
    </CardHeader>
    <CardContent>
      <form @submit="onSubmit" class="grid gap-4">
        <FormField
          v-slot="{ componentField }"
          name="name"
        >
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="text"
                placeholder="Your name"
                class="h-11 rounded-xl"
                :disabled="loading"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

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
                class="h-11 rounded-xl"
                :disabled="loading"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField
          v-slot="{ componentField }"
          name="password"
        >
          <FormItem>
            <FormLabel>Password</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="password"
                placeholder="Create a password"
                class="h-11 rounded-xl"
                :disabled="loading"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField
          v-slot="{ componentField }"
          name="confirmPassword"
        >
          <FormItem>
            <FormLabel>Confirm Password</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField"
                type="password"
                placeholder="Confirm your password"
                class="h-11 rounded-xl"
                :disabled="loading"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <div v-if="generalError" class="text-sm text-destructive">
          {{ generalError }}
        </div>

        <Button
          type="submit"
          class="h-11 w-full rounded-xl text-base font-semibold"
          :disabled="loading || !form.meta.value.valid"
        >
          <Loader2
            v-if="loading"
            class="mr-2 h-4 w-4 animate-spin"
          />
          {{ loading ? 'Creating account...' : 'Sign Up' }}
        </Button>

        <div class="mt-2 text-center text-sm text-muted-foreground">
          Already have an account?
          <router-link
            :to="{ name: 'login' }"
            class="font-semibold text-primary hover:text-primary/80"
            :tabindex="loading ? -1 : 0"
          >
            Login
          </router-link>
        </div>
      </form>
    </CardContent>
  </Card>
</template>
