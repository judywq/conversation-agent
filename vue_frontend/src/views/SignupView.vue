<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import SakuraCorner from '@/components/SakuraCorner.vue'
import SakuraMark from '@/components/SakuraMark.vue'
import { Eye, EyeOff, Loader2 } from 'lucide-vue-next'
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
const showPassword = ref(false)

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
  <Card class="relative mx-auto w-full overflow-hidden rounded-2xl border-border/80 shadow-lg shadow-primary/5 sm:w-[26rem]">
    <SakuraCorner class="opacity-80" :size="88" />
    <CardHeader class="relative z-[2] space-y-2 text-center">
      <div class="flex items-center justify-center gap-2">
        <SakuraMark :size="24" />
        <span class="text-lg font-bold tracking-[0.14em] uppercase">ConvAgent</span>
      </div>
      <CardTitle class="text-2xl font-bold">Create an account</CardTitle>
      <CardDescription>Join the campus dialogue</CardDescription>
    </CardHeader>
    <CardContent class="relative z-[2]">
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
              <div class="relative">
                <Input
                  v-bind="componentField"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="Create a password"
                  class="pr-10"
                  :disabled="loading"
                />
                <button
                  type="button"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  :disabled="loading"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="h-4 w-4" />
                  <Eye v-else class="h-4 w-4" />
                  <span class="sr-only">Toggle password visibility</span>
                </button>
              </div>
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
              <div class="relative">
                <Input
                  v-bind="componentField"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="Confirm your password"
                  class="pr-10"
                  :disabled="loading"
                />
                <button
                  type="button"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  :disabled="loading"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="h-4 w-4" />
                  <Eye v-else class="h-4 w-4" />
                  <span class="sr-only">Toggle password visibility</span>
                </button>
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <div v-if="generalError" class="text-sm text-destructive">
          {{ generalError }}
        </div>

        <Button
          type="submit"
          class="h-11 w-full text-base font-semibold"
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
