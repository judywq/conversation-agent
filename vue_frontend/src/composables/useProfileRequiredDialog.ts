import { ref } from 'vue'

/** Shared flag so the router can open the profile-required dialog without navigating. */
export const profileRequiredDialogOpen = ref(false)
