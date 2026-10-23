import { onScopeDispose, ref } from 'vue'

import type { PointCloud } from '@/api/generated'
import {
  getJob,
  PointCloudRequestError,
  startConversion,
  uploadPointCloud,
  waitForNextJobPoll,
} from './uploadApi'

const MAX_POLL_DURATION_MS = 5 * 60 * 1000
const MAX_CONSECUTIVE_POLL_ERRORS = 3

export type UploadStatus = 'idle' | 'uploading' | 'queued' | 'running' | 'done' | 'failed' | 'error'

export function useUpload() {
  const status = ref<UploadStatus>('idle')
  const error = ref<string | null>(null)
  const result = ref<PointCloud | null>(null)
  const progress = ref<number | null>(null)

  let controller: AbortController | null = null

  function reset(): void {
    controller?.abort()
    status.value = 'idle'
    error.value = null
    result.value = null
    progress.value = null
  }

  async function runConversion(pointCloudId: string, signal: AbortSignal): Promise<void> {
    const startedAt = Date.now()
    let consecutivePollErrors = 0
    let job = await startConversion(pointCloudId, signal)

    while (job.state === 'queued' || job.state === 'running') {
      if (Date.now() - startedAt >= MAX_POLL_DURATION_MS) {
        throw new PointCloudRequestError(
          'Conversion is taking longer than expected. Please try again.',
        )
      }

      status.value = job.state
      progress.value = job.progress
      await waitForNextJobPoll(signal)

      try {
        job = await getJob(job.id, signal)
        consecutivePollErrors = 0
      } catch (caught) {
        if (!(caught instanceof PointCloudRequestError) || !caught.retryable) throw caught

        consecutivePollErrors += 1
        if (consecutivePollErrors >= MAX_CONSECUTIVE_POLL_ERRORS) {
          throw new PointCloudRequestError(
            'Unable to check conversion status after several attempts. Please try again.',
          )
        }
      }
    }

    if (job.state !== 'succeeded') {
      throw new PointCloudRequestError(
        job.error?.message ??
          (job.state === 'cancelled'
            ? 'Conversion was cancelled.'
            : 'Conversion failed. Please try again.'),
      )
    }

    progress.value = job.progress ?? 100
    status.value = 'done'
  }

  function beginOperation(preserveResult = false): AbortController {
    controller?.abort()
    status.value = 'idle'
    error.value = null
    if (!preserveResult) result.value = null
    progress.value = null
    const current = new AbortController()
    controller = current
    return current
  }

  async function upload(file: File): Promise<void> {
    const current = beginOperation()
    status.value = 'uploading'
    let conversionStarted = false

    try {
      result.value = await uploadPointCloud(file, current.signal)
      conversionStarted = true
      await runConversion(result.value.id, current.signal)
    } catch (caught) {
      if (current.signal.aborted) return
      status.value = conversionStarted ? 'failed' : 'error'
      error.value =
        caught instanceof PointCloudRequestError
          ? caught.message
          : 'Conversion failed. Please try again.'
    }
  }

  async function retryConversion(): Promise<void> {
    if (!result.value) return

    const pointCloudId = result.value.id
    const current = beginOperation(true)
    try {
      await runConversion(pointCloudId, current.signal)
    } catch (caught) {
      if (current.signal.aborted) return
      status.value = 'failed'
      error.value =
        caught instanceof PointCloudRequestError
          ? caught.message
          : 'Conversion failed. Please try again.'
    }
  }

  onScopeDispose(() => controller?.abort())

  return { status, error, result, progress, upload, retryConversion, reset }
}
