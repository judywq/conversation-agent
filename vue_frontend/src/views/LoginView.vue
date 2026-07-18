<script setup lang="ts">
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { defaultAuthenticatedRoute } from '@/lib/authNavigation'
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import SakuraMark from '@/components/SakuraMark.vue';
import { Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-vue-next';
import { storeToRefs } from 'pinia';
import { useForm } from 'vee-validate';
import { toTypedSchema } from '@vee-validate/zod';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { loginFormSchema } from '@/lib/validations'

const authStore = useAuthStore();
const { loading } = storeToRefs(authStore);
const router = useRouter();
const route = useRoute();
const showPassword = ref(false);

const form = useForm({
  validationSchema: toTypedSchema(loginFormSchema),
  initialValues: {
    email: '',
    password: '',
  },
});

const generalError = ref<string | null>(null);

const onSubmit = form.handleSubmit(async (values) => {
  try {
    generalError.value = null;
    await authStore.login(values.email, values.password);

    if (authStore.isAuthenticated) {
      const redirectPath = typeof route.query.redirect === 'string'
        ? route.query.redirect
        : defaultAuthenticatedRoute();
      router.push(redirectPath);
    }
  } catch (err: any) {
    if (err.fieldErrors) {
      form.setErrors(err.fieldErrors)
    }
    if (err.nonFieldError) {
      generalError.value = err.nonFieldError;
    }
  }
});
</script>

<template>
  <Card class="mx-auto w-full overflow-hidden rounded-2xl border-border/80 shadow-lg shadow-primary/5 sm:w-[26rem]">
    <CardHeader class="space-y-3 pb-2 text-center">
      <div class="flex items-center justify-center gap-2">
        <SakuraMark :size="26" />
        <span class="text-lg font-bold tracking-[0.14em] text-foreground uppercase">ConvAgent</span>
      </div>
      <CardTitle class="text-2xl font-bold text-foreground">Welcome back</CardTitle>
    </CardHeader>
    <CardContent class="pt-2">
      <form @submit="onSubmit" class="grid gap-4">
        <FormField
          v-slot="{ componentField }"
          name="email"
        >
          <FormItem>
            <FormLabel>Email</FormLabel>
            <FormControl>
              <div class="relative">
                <Mail class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  v-bind="componentField"
                  type="email"
                  placeholder="name@example.com"
                  class="h-11 rounded-xl pl-10"
                  :disabled="loading"
                />
              </div>
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField
          v-slot="{ componentField }"
          name="password"
        >
          <FormItem>
            <div class="flex items-center">
              <FormLabel>Password</FormLabel>
              <router-link
                :to="{ name: 'forgot-password'}"
                class="ml-auto inline-block text-sm font-medium text-primary hover:text-primary/80"
                :tabindex="loading ? -1 : 0"
              >
                Forgot password?
              </router-link>
            </div>
            <FormControl>
              <div class="relative">
                <Lock class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  v-bind="componentField"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="Enter your password"
                  class="h-11 rounded-xl pl-10 pr-10"
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

        <Button
          type="submit"
          class="mt-1 h-11 w-full rounded-xl text-base font-semibold"
          :disabled="loading || !form.meta.value.valid"
        >
          <Loader2
            v-if="loading"
            class="mr-2 h-4 w-4 animate-spin"
          />
          <template v-if="loading">Logging in...</template>
          <template v-else>
            Enter Campus
            <SakuraMark :size="16" class="text-primary-foreground" />
          </template>
        </Button>

        <div v-if="generalError" class="text-sm text-destructive">
          {{ generalError }}
        </div>

        <div class="mt-2 text-center text-sm text-muted-foreground">
          New here?
          <router-link
            :to="{ name: 'signup' }"
            class="font-semibold text-primary hover:text-primary/80"
            :tabindex="loading ? -1 : 0"
          >
            Create an account
          </router-link>
        </div>
      </form>
    </CardContent>
  </Card>
</template>
