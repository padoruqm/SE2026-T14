import { onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { cropPointCloud, type Job } from '@/api/generated'
import { JobWaitError, waitForJob } from '@/api/jobs'
import { apiBaseUrl } from '@/shared/config'

import type { CropBounds } from './cropBounds'

export type CropOutputFormat = 'las' | 'laz'
export type CropRequestState = 'idle' | 'submitting' | 'queued' | 'running' | 'succeeded' | 'failed'

const NETWORK = 'Could not reach the server. Check your connection and try again.'

// Fixed text per error code, so no server message, path or stack trace reaches the screen.
const START_ERRORS: Record<string, string> = {
  NOT_FOUND: 'This point cloud was not found.',
  GONE: 'This point cloud is no longer available.',
  CONFLICT: 'This point cloud is not ready to crop yet. Wait for its conversion to finish.',
  VALIDATION_ERROR: 'The crop region is not valid.',
  BAD_REQUEST: 'The crop region is not valid.',
  INVALID_POINT_CLOUD: 'This point cloud could not be cropped.',
}
const START_FALLBACK = 'The crop could not be started. Please try again.'
const JOB_ERRORS: Record<string, string> = {
  INVALID_POINT_CLOUD: 'This point cloud could not be cropped.',
}
const JOB_FALLBACK = 'The crop failed. Please try again.'

function errorCode(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('error' in error)) return null
  const body = error.error
  if (typeof body !== 'object' || body === null || !('code' in body)) return null
  return typeof body.code === 'string' ? body.code : null
}

function lookup(table: Record<string, string>, code: string | null | undefined) {
  return code && Object.prototype.hasOwnProperty.call(table, code) ? table[code] : undefined
}

/**
 * Send a crop request for one point cloud and follow its job until it ends. The
 * result is a new point cloud (`resultId`); the source is never changed.
 */
export function useCropRequest(pointCloudId: MaybeRefOrGetter<string>) {
  const state = ref<CropRequestState>('idle')
  const progress = ref<number | null>(null)
  const resultId = ref<string | null>(null)
  const error = ref<string | null>(null)
  const retryable = ref(false)

  let controller: AbortController | null = null
  let last: { bounds: CropBounds; format: CropOutputFormat } | null = null

  function fail(message: string, canRetry: boolean): void {
    state.value = 'failed'
    error.value = message
    retryable.value = canRetry
  }

  function show(job: Job): void {
    if (job.state === 'queued' || job.state === 'running') state.value = job.state
    progress.value = job.progress
  }

  async function submit(bounds: CropBounds, format: CropOutputFormat): Promise<void> {
    if (state.value === 'submitting' || state.value === 'queued' || state.value === 'running') {
      return
    }
    controller?.abort()
    const current = new AbortController()
    controller = current
    last = { bounds: { ...bounds }, format }
    state.value = 'submitting'
    progress.value = null
    resultId.value = null
    error.value = null
    retryable.value = false

    let job: Job
    try {
      const response = await cropPointCloud({
        baseUrl: apiBaseUrl,
        path: { id: toValue(pointCloudId) },
        body: { bounds: last.bounds, outputFormat: format },
        signal: current.signal,
        throwOnError: true,
      })
      job = response.data
    } catch (caught) {
      if (current.signal.aborted) return
      if (caught instanceof TypeError) return fail(NETWORK, true)
      const message = lookup(START_ERRORS, errorCode(caught))
      return fail(message ?? START_FALLBACK, message === undefined)
    }

    try {
      const finished = await waitForJob(job, { signal: current.signal, onUpdate: show })
      if (current.signal.aborted) return
      if (finished.state === 'succeeded' && finished.resultId) {
        state.value = 'succeeded'
        progress.value = 100
        resultId.value = finished.resultId
      } else if (finished.state === 'cancelled') {
        fail('The crop was cancelled.', true)
      } else {
        fail(lookup(JOB_ERRORS, finished.error?.code) ?? JOB_FALLBACK, true)
      }
    } catch (caught) {
      if (current.signal.aborted) return
      if (caught instanceof JobWaitError && caught.reason === 'timeout') {
        return fail('The crop is taking longer than expected. Check again later.', true)
      }
      if (caught instanceof JobWaitError) return fail(NETWORK, true)
      fail(JOB_FALLBACK, true)
    }
  }

  function retry(): Promise<void> {
    return last && state.value === 'failed' ? submit(last.bounds, last.format) : Promise.resolve()
  }

  function reset(): void {
    controller?.abort()
    controller = null
    state.value = 'idle'
    progress.value = null
    resultId.value = null
    error.value = null
    retryable.value = false
  }

  // A different point cloud starts from scratch; a request for the old one is dropped.
  watch(() => toValue(pointCloudId), reset)
  onScopeDispose(() => controller?.abort())

  return { state, progress, resultId, error, retryable, submit, retry, reset }
}
