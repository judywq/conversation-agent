<script setup lang="ts">
import NavBar from '@/components/NavBar.vue';
import SceneBackdrop from '@/components/SceneBackdrop.vue';
import { hideAppNav } from '@/composables/useLayoutChrome';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import { onMounted } from 'vue';

const authStore = useAuthStore();
const router = useRouter();

// Redirect unauthenticated users to login
onMounted(() => {
  if (!authStore.isAuthenticated && router.currentRoute.value.meta.requiresAuth) {
    router.push({ name: 'login' });
  }
});
</script>

<template>
  <div class="relative min-h-screen flex flex-col bg-background">
    <SceneBackdrop />

    <NavBar v-if="!hideAppNav" />

    <main class="relative z-10 flex-grow">
      <router-view v-slot="{ Component, route }">
        <transition name="fade" appear>
          <component :is="Component" :key="route.fullPath" />
        </transition>
      </router-view>
    </main>
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
