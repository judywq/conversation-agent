<script setup lang="ts">
const currentYear = new Date().getFullYear()
</script>

<template>
  <footer class="border-t border-border/70 bg-card/60 py-6 backdrop-blur-sm">
    <div class="container mx-auto px-4">
      <div class="text-center text-sm text-muted-foreground">
        <p>&copy; {{ currentYear }} Judy Wang. All rights reserved.</p>
        <div class="mt-2 space-x-4">
          <a href="mailto:judy.wang@aoni.waseda.jp" class="font-medium text-primary transition-colors hover:text-primary/80">
            Contact Us
          </a>
        </div>
      </div>
    </div>
  </footer>
</template>
