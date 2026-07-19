<script setup lang="ts">
import Footer from '@/components/Footer.vue';
import NavBar from '@/components/NavBar.vue';
import SceneBackdrop from '@/components/SceneBackdrop.vue';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { hideAppNav } from '@/composables/useLayoutChrome';
import { profileRequiredDialogOpen } from '@/composables/useProfileRequiredDialog';
import { useAuthStore } from '@/stores/auth';
import { useRoute, useRouter } from 'vue-router';
import { computed, onMounted } from 'vue';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const showFooter = computed(() => route.name === 'home');

// Redirect unauthenticated users to login
onMounted(() => {
  if (!authStore.isAuthenticated && router.currentRoute.value.meta.requiresAuth) {
    router.push({ name: 'login' });
  }
});

function dismissProfileRequired() {
  profileRequiredDialogOpen.value = false;
}

async function confirmProfileRequired() {
  profileRequiredDialogOpen.value = false;
  await router.push({ name: 'profile' });
}
</script>

<template>
  <div class="relative min-h-screen flex flex-col bg-background">
    <SceneBackdrop />

    <NavBar v-if="!hideAppNav" />

    <main class="relative z-10 flex-grow">
      <router-view v-slot="{ Component, route }">
        <!-- path (not fullPath): query-only changes must not remount; out-in: avoid leave+enter stacking which jumps content up from below.
             :duration forces leave/enter to finish even if transitionend is cancelled
             (e.g. exitFullscreen during route leave). Child views must be single-root
             (no leading HTML comments) or out-in leaves main blank. -->
        <transition name="fade" mode="out-in" appear :duration="200">
          <component :is="Component" :key="route.path" />
        </transition>
      </router-view>
    </main>

    <div v-if="showFooter" class="relative z-10">
      <Footer />
    </div>

    <Dialog v-model:open="profileRequiredDialogOpen">
      <DialogContent @open-auto-focus.prevent>
        <DialogHeader>
          <DialogTitle>Complete your profile</DialogTitle>
          <DialogDescription>
            Please finish your profile before starting a conversation.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="gap-3 sm:gap-x-3">
          <Button variant="outline" @click="dismissProfileRequired">Cancel</Button>
          <Button @click="confirmProfileRequired">OK</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
