<script setup lang="ts">
import { computed, ref } from 'vue'

import { useUpload } from './useUpload'
import { validateUploadFile } from './uploadValidation'

const { status, error, result, upload, reset } = useUpload()
const selectedFile = ref<File | null>(null)
const validationError = ref<string | null>(null)

const isUploading = computed(() => status.value === 'uploading')
const isProcessing = computed(() => status.value === 'queued' || status.value === 'running')
const message = computed(() => validationError.value ?? error.value)

function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  reset()
  selectedFile.value = file
  validationError.value = file ? validateUploadFile(file) : null
}

function submit() {
  if (selectedFile.value && !validationError.value) upload(selectedFile.value)
}
</script>

<template>
  <form class="upload-form" @submit.prevent="submit">
    <label for="point-cloud-file">Point cloud file (.las, .laz)</label>
    <input
      id="point-cloud-file"
      type="file"
      accept=".las,.laz"
      :disabled="isUploading"
      @change="onFileChange"
    />

    <button
      type="submit"
      :disabled="!selectedFile || !!validationError || isUploading || isProcessing"
    >
      {{ isUploading ? 'Uploading…' : isProcessing ? 'Converting…' : 'Upload' }}
    </button>

    <div aria-live="polite">
      <p v-if="message" role="alert" class="upload-error">{{ message }}</p>
      <button v-if="status === 'failed' || status === 'error'" type="button" @click="submit">
        Try again
      </button>
      <p v-if="status === 'queued'" role="status">Conversion queued…</p>
      <p v-if="status === 'running'" role="status">Conversion in progress…</p>
      <p v-if="status === 'failed'" role="status">Conversion failed.</p>
      <p v-if="status === 'done' && result" role="status">
        Conversion complete for {{ result.filename }} (ID: {{ result.id }}).
      </p>
    </div>
  </form>
</template>

<style scoped>
.upload-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.upload-error {
  color: #b00020;
}
</style>
