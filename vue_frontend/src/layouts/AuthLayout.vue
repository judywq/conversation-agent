<script setup lang="ts">
import Footer from '@/components/Footer.vue';
import SakuraMark from '@/components/SakuraMark.vue';
import { defaultAuthenticatedRoute } from '@/lib/authNavigation';
import { ensureCsrfToken } from '@/services/api';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { onMounted } from 'vue';

const authStore = useAuthStore();
const router = useRouter();

// Redirect authenticated users away from auth routes
onMounted(() => {
  void ensureCsrfToken().catch(() => {});

  if (authStore.isAuthenticated) {
    router.push(defaultAuthenticatedRoute());
  }
});
</script>

<template>
  <div class="relative min-h-screen flex flex-col overflow-hidden bg-background">
    <div
      class="pointer-events-none absolute inset-0 bg-cover bg-center scale-105 blur-sm brightness-95"
      style="background-image: url('/scenes/classroom.png')"
      aria-hidden="true"
    />
    <div class="pointer-events-none absolute inset-0 bg-background/55 sakura-petals" aria-hidden="true" />

    <nav class="relative z-10 w-full py-5">
      <div class="container mx-auto px-4">
        <router-link
          :to="{ name: 'home' }"
          class="flex items-center justify-center gap-2 text-foreground"
        >
          <SakuraMark :size="28" />
          <span class="text-2xl font-bold tracking-[0.12em] uppercase">ConvAgent</span>
        </router-link>
      </div>
    </nav>

    <main class="relative z-10 flex-grow flex items-start justify-center px-4 py-6 sm:py-10">
      <div class="w-full max-w-md">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in" appear>
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>

    <div class="relative z-10">
      <Footer />
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
