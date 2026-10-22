<script setup lang="ts">
import MetadataPanel from './MetadataPanel.vue'

defineProps<{ id: string }>()
</script>

<template>
  <section>
    <h1>Viewer</h1>
    <p>Point cloud: {{ id }}</p>
    <MetadataPanel :id="id" />
  </section>
</template>
