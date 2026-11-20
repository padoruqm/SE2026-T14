<script setup lang="ts">
import { computed } from 'vue'

import type { Vec3 } from '@/features/measure'

import { BOX_EDGES, boxCorners, type CropBounds } from './cropBounds'

interface ScreenPoint {
  x: number
  y: number
  visible: boolean
}

const props = defineProps<{
  /** The region to outline, or null. */
  bounds: CropBounds | null
  /** Corners picked so far, drawn as markers before the box exists. */
  corners: Vec3[]
  project: (point: Vec3) => ScreenPoint
  /** Changes whenever the view moves, so the outline is placed again. */
  version: number
}>()

const edges = computed(() => {
  // Reading the version makes this recompute after every frame.
  void props.version
  if (!props.bounds) return []
  const screen = boxCorners(props.bounds).map((corner) => props.project(corner))
  return BOX_EDGES.flatMap(([from, to]) => {
    const a = screen[from]
    const b = screen[to]
    return a?.visible && b?.visible ? [{ a, b }] : []
  })
})

const markers = computed(() => {
  void props.version
  return props.corners.map((corner) => props.project(corner)).filter((point) => point.visible)
})
</script>

<template>
  <svg class="crop-overlay" aria-hidden="true">
    <line
      v-for="(edge, index) in edges"
      :key="index"
      :x1="edge.a.x"
      :y1="edge.a.y"
      :x2="edge.b.x"
      :y2="edge.b.y"
      class="crop-edge"
    />
    <circle
      v-for="(marker, index) in markers"
      :key="`m${index}`"
      :cx="marker.x"
      :cy="marker.y"
      r="5"
      class="crop-marker"
    />
  </svg>
</template>

<style scoped>
.crop-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.crop-edge {
  stroke: #00e0ff;
  stroke-width: 2;
}

.crop-marker {
  fill: #00e0ff;
  stroke: #000;
  stroke-width: 1.5;
}
</style>
