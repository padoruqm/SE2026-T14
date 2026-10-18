<script setup lang="ts">
defineProps<{ id: string }>()
</script>

<template>
  <section>
    <h1>Viewer</h1>
    <p>Point cloud: {{ id }}</p>
  </section>
</template>
