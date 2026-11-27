<script setup lang="ts">
import { ref } from 'vue'

import { downloadPointCloud } from '@/api/generated'
import { apiBaseUrl } from '@/shared/config'

const props = defineProps<{
  id: string
  filename: string
  ready: boolean
}>()

const downloading = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const NETWORK_ERROR = 'Could not reach the server. Check your connection and try again.'
const DOWNLOAD_ERRORS: Record<string, string> = {
  CONFLICT: 'This point cloud is not ready to download yet.',
  NOT_FOUND: 'This point cloud was not found.',
  GONE: 'This point cloud is no longer available to download.',
}

function errorCode(caught: unknown): string | null {
  if (typeof caught !== 'object' || caught === null || !('error' in caught)) return null
  const body = caught.error
  if (typeof body !== 'object' || body === null || !('code' in body)) return null
  return typeof body.code === 'string' ? body.code : null
}

function requestErrorMessage(caught: unknown): string {
  if (caught instanceof TypeError) return NETWORK_ERROR
  const code = errorCode(caught)
  const message =
    code !== null && Object.prototype.hasOwnProperty.call(DOWNLOAD_ERRORS, code)
      ? DOWNLOAD_ERRORS[code]
      : undefined
  return message ?? 'Could not download this point cloud. Please try again.'
}

async function download(): Promise<void> {
  if (!props.ready || downloading.value) return
  downloading.value = true
  error.value = null
  success.value = null

  let file: Blob
  try {
    const response = await downloadPointCloud({
      baseUrl: apiBaseUrl,
      path: { id: props.id },
      throwOnError: true,
    })
    file = response.data
  } catch (caught) {
    error.value = requestErrorMessage(caught)
    downloading.value = false
    return
  }

  let objectUrl: string | null = null
  try {
    objectUrl = URL.createObjectURL(file)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = props.filename
    link.hidden = true
    document.body.append(link)
    try {
      link.click()
    } finally {
      link.remove()
    }
    success.value = 'Download started.'
  } catch {
    error.value = 'Could not start the download. Please try again.'
  } finally {
    const urlToRevoke = objectUrl
    if (urlToRevoke !== null) {
      window.setTimeout(() => URL.revokeObjectURL(urlToRevoke), 1000)
    }
    downloading.value = false
  }
}
</script>

<template>
  <section class="download-panel" aria-labelledby="download-heading" :aria-busy="downloading">
    <h3 id="download-heading">Download</h3>
    <button type="button" :disabled="!ready || downloading" @click="download">
      {{ downloading ? 'Preparing download…' : 'Download LAS/LAZ' }}
    </button>
    <p v-if="!ready" class="download-hint">
      Download is available once processing is complete.
    </p>
    <p v-if="success" role="status">{{ success }}</p>
    <p v-if="error" role="alert" class="download-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.download-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.download-panel h3 {
  margin-bottom: 0;
}

.download-hint {
  color: #555;
}

.download-error {
  color: #b00020;
}
</style>
