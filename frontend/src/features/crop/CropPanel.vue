<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

import {
  CROP_ERROR_MESSAGES,
  isFiniteBounds,
  normalizeBounds,
  type CropBounds,
  type CropError,
} from './cropBounds'

const props = defineProps<{
  picking: boolean
  /** Corners picked so far (0 to 2). */
  cornerCount: number
  /** The region as selected, valid or not. */
  selection: CropBounds | null
  /** The valid box that would be sent, after reordering and clamping. */
  bounds: CropBounds | null
  error: CropError | null
  crs: string | null
}>()

const emit = defineEmits<{
  togglePicking: []
  change: [bounds: CropBounds]
  clear: []
}>()

const FIELDS = [
  ['minX', 'Min X'],
  ['maxX', 'Max X'],
  ['minY', 'Min Y'],
  ['maxY', 'Max Y'],
  ['minZ', 'Min Z'],
  ['maxZ', 'Max Z'],
] as const

// What the user is typing. Kept as text so a half-typed number is not rewritten.
const draft = reactive<Record<keyof CropBounds, string>>({
  minX: '',
  minY: '',
  minZ: '',
  maxX: '',
  maxY: '',
  maxZ: '',
})

watch(
  () => props.selection,
  (selection) => {
    for (const [key] of FIELDS) draft[key] = selection ? String(selection[key]) : ''
  },
  { immediate: true },
)

const hasSelection = computed(() => props.selection !== null || props.cornerCount > 0)
const clamped = computed(() => {
  const { bounds, selection } = props
  if (!bounds || !selection || !isFiniteBounds(selection)) return false
  const wanted = normalizeBounds(selection)
  return FIELDS.some(([key]) => bounds[key] !== wanted[key])
})

function commit(): void {
  const values = FIELDS.map(([key]) => [key, String(draft[key]).trim()] as const)
  // Wait until every field has something in it.
  if (values.some(([, text]) => text === '')) return
  const next = Object.fromEntries(values.map(([key, text]) => [key, Number(text)])) as unknown
  emit('change', next as CropBounds)
}
</script>

<template>
  <section class="crop-panel" aria-labelledby="crop-heading">
    <h2 id="crop-heading">Crop region</h2>

    <button type="button" :aria-pressed="picking" @click="emit('togglePicking')">
      {{ picking ? 'Stop picking' : 'Pick region' }}
    </button>

    <p v-if="picking">
      {{
        cornerCount === 0
          ? 'Click one corner of the region in the viewer.'
          : 'Click the opposite corner.'
      }}
    </p>

    <p v-if="crs">Coordinates are world coordinates ({{ crs }}).</p>
    <p v-else>Coordinates are world coordinates.</p>

    <div class="crop-fields">
      <label v-for="[key, label] in FIELDS" :key="key">
        {{ label }}
        <input v-model="draft[key]" type="number" step="any" @change="commit" />
      </label>
    </div>

    <p v-if="error" role="alert" class="crop-error">{{ CROP_ERROR_MESSAGES[error] }}</p>

    <div role="status">
      <template v-if="bounds">
        <p v-if="clamped">The region was cut to the point cloud.</p>
        <dl class="crop-result">
          <dt>Min</dt>
          <dd>{{ bounds.minX }}, {{ bounds.minY }}, {{ bounds.minZ }}</dd>
          <dt>Max</dt>
          <dd>{{ bounds.maxX }}, {{ bounds.maxY }}, {{ bounds.maxZ }}</dd>
        </dl>
      </template>
    </div>

    <button v-if="hasSelection" type="button" @click="emit('clear')">Clear</button>
  </section>
</template>

<style scoped>
.crop-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem 1rem;
}

.crop-fields label {
  display: grid;
  gap: 0.125rem;
}

.crop-result {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  font-variant-numeric: tabular-nums;
}

.crop-result dt {
  font-weight: 600;
}

.crop-result dd {
  margin: 0;
}

.crop-error {
  color: #b00020;
}
</style>
