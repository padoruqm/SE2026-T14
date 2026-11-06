<script setup lang="ts">
import { computed } from 'vue'

import type { Vec3 } from './measurement'

interface ScreenPoint {
  x: number
  y: number
  visible: boolean
}

const props = defineProps<{
  points: Vec3[]
  project: (point: Vec3) => ScreenPoint
  /** Changes whenever the view moves, so the markers are placed again. */
  version: number
  label: string | null
}>()

const screen = computed(() => {
  // Reading the version makes this recompute after every frame.
  void props.version
  return props.points.map((point) => props.project(point))
})
const markers = computed(() => screen.value.filter((point) => point.visible))
const line = computed(() => {
  const [from, to] = screen.value
  return from?.visible && to?.visible ? { from, to } : null
})
</script>

<template>
  <svg class="measure-overlay" aria-hidden="true">
    <line
      v-if="line"
      :x1="line.from.x"
      :y1="line.from.y"
      :x2="line.to.x"
      :y2="line.to.y"
      class="measure-line"
    />
    <circle
      v-for="(marker, index) in markers"
      :key="index"
      :cx="marker.x"
      :cy="marker.y"
      r="5"
      class="measure-marker"
    />
    <text
      v-if="line && label"
      :x="(line.from.x + line.to.x) / 2"
      :y="(line.from.y + line.to.y) / 2 - 8"
      text-anchor="middle"
      class="measure-label"
    >
      {{ label }}
    </text>
  </svg>
</template>

<style scoped>
.measure-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.measure-line {
  stroke: #ffd400;
  stroke-width: 2;
}

.measure-marker {
  fill: #ffd400;
  stroke: #000;
  stroke-width: 1.5;
}

.measure-label {
  fill: #fff;
  stroke: #000;
  stroke-width: 3;
  paint-order: stroke;
  font: 600 13px sans-serif;
}
</style>
