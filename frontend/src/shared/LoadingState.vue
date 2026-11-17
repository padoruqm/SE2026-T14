<script setup lang="ts">
withDefaults(defineProps<{ label?: string }>(), { label: 'Loading…' })
</script>

<template>
  <p role="status" aria-busy="true">{{ label }}</p>
</template>
