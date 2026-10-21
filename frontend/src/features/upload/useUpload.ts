import { onScopeDispose, ref } from 'vue'

import { UploadError, uploadPointCloud, type PointCloud } from './uploadApi'

export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'

export function useUpload() {
  const status = ref<UploadStatus>('idle')
  const error = ref<string | null>(null)
  const result = ref<PointCloud | null>(null)

  let controller: AbortController | null = null

  function reset(): void {
    controller?.abort()
    status.value = 'idle'
    error.value = null
    result.value = null
  }

  async function upload(file: File): Promise<void> {
    reset()
    const current = new AbortController()
    controller = current
    status.value = 'uploading'

    try {
      result.value = await uploadPointCloud(file, current.signal)
      status.value = 'success'
    } catch (caught) {
      if (current.signal.aborted) return
      status.value = 'error'
      error.value =
        caught instanceof UploadError ? caught.message : 'Upload failed. Please try again.'
    }
  }

  // Abort the in-flight request when the owning component unmounts.
  onScopeDispose(() => controller?.abort())

  return { status, error, result, upload, reset }
}
