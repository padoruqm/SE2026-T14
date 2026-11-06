<script setup lang="ts">
import { computed, nextTick, useTemplateRef, watch } from 'vue'

import { distanceUnit, formatLength } from './units'
import type { DistanceMeasurement, Vec3 } from './measurement'

const props = defineProps<{
  active: boolean
  coordinates: Vec3 | null
  measurement: DistanceMeasurement | null
  confirmingClear: boolean
  crs: string | null
}>()

defineEmits<{
  toggle: []
  requestClear: []
  confirmClear: []
  cancelClear: []
}>()

const unit = computed(() => distanceUnit(props.crs))
const hasResult = computed(() => props.coordinates !== null || props.measurement !== null)
const keepButton = useTemplateRef<HTMLButtonElement>('keepButton')

// Angles need far more decimals than metres to say anything useful.
function axis(value: number): string {
  return value.toFixed(unit.value.geographic ? 7 : 3)
}

function length(value: number): string {
  return formatLength(value, props.crs)
}

function point(p: Vec3): string {
  return `${axis(p.x)}, ${axis(p.y)}, ${axis(p.z)}`
}

watch(
  () => props.confirmingClear,
  async (confirming) => {
    if (!confirming) return
    await nextTick()
    keepButton.value?.focus()
  },
)
</script>

<template>
  <section class="measure-panel" aria-labelledby="measure-heading">
    <h2 id="measure-heading">Measure</h2>

    <button type="button" :aria-pressed="active" @click="$emit('toggle')">
      {{ active ? 'Stop measuring' : 'Measure' }}
    </button>

    <p v-if="active && !hasResult">
      Click a point in the viewer to read its coordinates, then a second point to measure the
      distance.
    </p>

    <div role="status">
      <dl v-if="coordinates" class="measure-results">
        <dt>X</dt>
        <dd>{{ axis(coordinates.x) }}</dd>
        <dt>Y</dt>
        <dd>{{ axis(coordinates.y) }}</dd>
        <dt>Z</dt>
        <dd>{{ axis(coordinates.z) }}</dd>
      </dl>

      <template v-else-if="measurement">
        <p v-if="unit.geographic" class="measure-warning">
          This point cloud uses angular coordinates (degrees), so a straight-line distance would be
          meaningless. Use a projected CRS to measure distances.
        </p>
        <dl v-else class="measure-results">
          <dt>Distance</dt>
          <dd>{{ length(measurement.distance) }}</dd>
          <dt>Horizontal</dt>
          <dd>{{ length(measurement.horizontal) }}</dd>
          <dt>Vertical</dt>
          <dd>{{ length(measurement.vertical) }}</dd>
        </dl>
        <dl class="measure-results">
          <dt>From</dt>
          <dd>{{ point(measurement.from) }}</dd>
          <dt>To</dt>
          <dd>{{ point(measurement.to) }}</dd>
        </dl>
      </template>
    </div>

    <div v-if="hasResult && !confirmingClear">
      <button type="button" @click="$emit('requestClear')">Clear measurement</button>
    </div>

    <div v-if="confirmingClear" role="group" aria-labelledby="measure-confirm">
      <p id="measure-confirm">Delete this measurement? The point cloud is not changed.</p>
      <button type="button" @click="$emit('confirmClear')">Delete</button>
      <button ref="keepButton" type="button" @click="$emit('cancelClear')">Keep</button>
    </div>
  </section>
</template>

<style scoped>
.measure-results {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  font-variant-numeric: tabular-nums;
}

.measure-results dt {
  font-weight: 600;
}

.measure-results dd {
  margin: 0;
}

.measure-warning {
  color: #b00020;
}
</style>
