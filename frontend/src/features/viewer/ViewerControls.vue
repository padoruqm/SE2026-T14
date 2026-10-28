<script setup lang="ts">
import type { ColorMode } from './potreeViewer'

const pointSize = defineModel<number>('pointSize', { required: true })
const colorMode = defineModel<ColorMode>('colorMode', { required: true })

defineEmits<{ resetView: [] }>()
</script>

<template>
  <form class="viewer-controls" @submit.prevent>
    <label>
      Point size
      <input v-model.number="pointSize" type="range" min="1" max="5" step="0.5" />
    </label>
    <label>
      Color
      <select v-model="colorMode">
        <option value="rgb">RGB</option>
        <option value="elevation">Elevation</option>
        <option value="intensity">Intensity</option>
      </select>
    </label>
    <button type="button" @click="$emit('resetView')">Reset view</button>
  </form>
</template>

<style scoped>
.viewer-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
</style>
