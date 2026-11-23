<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import type { CropBounds } from './cropBounds'
import type { CropOutputFormat, CropRequestState } from './useCropRequest'

const props = defineProps<{
  /** The valid region to crop, or null while there is none. */
  bounds: CropBounds | null
  state: CropRequestState
  progress: number | null
  resultId: string | null
  error: string | null
  retryable: boolean
}>()

const emit = defineEmits<{
  submit: [format: CropOutputFormat]
  retry: []
}>()

const format = ref<CropOutputFormat>('laz')

const busy = computed(
  () => props.state === 'submitting' || props.state === 'queued' || props.state === 'running',
)
const canSubmit = computed(() => props.bounds !== null && !busy.value)
const statusText = computed(() => {
  switch (props.state) {
    case 'submitting':
      return 'Sending the crop request…'
    case 'queued':
      return 'Crop queued…'
    case 'running':
      return props.progress === null ? 'Cropping…' : `Cropping… ${props.progress}%`
    case 'succeeded':
      return 'Crop complete. The original point cloud is unchanged.'
    default:
      return ''
  }
})
</script>

<template>
  <section class="crop-request" aria-labelledby="crop-request-heading">
    <h3 id="crop-request-heading">Crop</h3>

    <label>
      Output format
      <select v-model="format" :disabled="busy">
        <option value="laz">LAZ (compressed)</option>
        <option value="las">LAS</option>
      </select>
    </label>

    <button
      type="button"
      :disabled="!canSubmit"
      aria-describedby="crop-request-hint"
      @click="emit('submit', format)"
    >
      Crop point cloud
    </button>
    <p v-if="!bounds" id="crop-request-hint" class="crop-request-hint">
      Select a valid region to crop.
    </p>

    <div role="status">
      <p v-if="statusText">{{ statusText }}</p>
      <progress
        v-if="state === 'running' && progress !== null"
        :value="progress"
        max="100"
        aria-label="Crop progress"
      />
      <RouterLink v-if="state === 'succeeded' && resultId" :to="`/viewer/${resultId}`">
        Open the cropped point cloud
      </RouterLink>
    </div>

    <div v-if="state === 'failed' && error">
      <p role="alert" class="crop-request-error">{{ error }}</p>
      <button v-if="retryable" type="button" @click="emit('retry')">Try again</button>
    </div>
  </section>
</template>

<style scoped>
.crop-request {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.crop-request-hint {
  color: #555;
}

.crop-request-error {
  color: #b00020;
}
</style>
