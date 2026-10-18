<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <header class="app-header">
    <RouterLink to="/upload" class="app-title">Point Cloud Explorer</RouterLink>
  </header>
  <main>
    <RouterView />
  </main>
</template>

<style scoped>
.app-header {
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid #ddd;
}

.app-title {
  font-weight: 600;
  color: inherit;
  text-decoration: none;
}
</style>
