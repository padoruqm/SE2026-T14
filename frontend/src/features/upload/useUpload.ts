import { onScopeDispose, ref } from 'vue'

import type { PointCloud } from '@/api/generated/types.gen'
import {
  getJob,
  PointCloudRequestError,
  startConversion,
  uploadPointCloud,
  waitForNextJobPoll,
} from './uploadApi'

export type UploadStatus =
  | 'idle'
  | 'uploading'
  | 'queued'
  | 'running'
  | 'done'
  | 'failed'
  | 'error'

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
    let conversionStarted = false

    try {
      result.value = await uploadPointCloud(file, current.signal)
      conversionStarted = true
      let job = await startConversion(result.value.id, current.signal)

      while (job.state === 'queued' || job.state === 'running') {
        status.value = job.state
        await waitForNextJobPoll(current.signal)
        job = await getJob(job.id, current.signal)
      }

      if (job.state !== 'succeeded') {
        throw new PointCloudRequestError(
          job.error?.message ??
            (job.state === 'cancelled'
              ? 'Conversion was cancelled.'
              : 'Conversion failed. Please try again.'),
        )
      }

      status.value = 'done'
    } catch (caught) {
      if (current.signal.aborted) return
      status.value = conversionStarted ? 'failed' : 'error'
      error.value =
        caught instanceof PointCloudRequestError
          ? caught.message
          : 'Conversion failed. Please try again.'
    }
  }

  // Abort the in-flight request when the owning component unmounts.
  onScopeDispose(() => controller?.abort())

  return { status, error, result, upload, reset }
}
