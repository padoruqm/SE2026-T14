<script setup lang="ts">
defineProps<{ title: string; message?: string }>()
</script>

<template>
  <section role="status">
    <h2>{{ title }}</h2>
    <p v-if="message">{{ message }}</p>
    <slot />
  </section>
</template>
