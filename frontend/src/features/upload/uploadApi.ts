import {
  convertPointCloud as convertPointCloudRequest,
  getJob as getJobRequest,
  uploadPointCloud as uploadPointCloudRequest,
} from '@/api/generated'
import type { Job, PointCloud } from '@/api/generated'
import { createClient } from '@/api/generated/client'
import { apiBaseUrl } from '@/shared/config'

const client = createClient({ baseUrl: apiBaseUrl })

export class PointCloudRequestError extends Error {
  constructor(
    message: string,
    readonly retryable = false,
  ) {
    super(message)
  }
}

const NETWORK_ERROR_MESSAGE = 'Could not reach the server. Check your connection and try again.'
const UNEXPECTED_ERROR_MESSAGE = 'The server returned an unexpected response. Please try again.'

function getApiErrorMessage(error: unknown): string | null {
  if (
    typeof error === 'object' &&
    error !== null &&
    'error' in error &&
    typeof error.error === 'object' &&
    error.error !== null &&
    'message' in error.error &&
    typeof error.error.message === 'string'
  ) {
    return error.error.message
  }
  return null
}

async function request<T>(operation: () => Promise<{ data: T }>, signal: AbortSignal): Promise<T> {
  try {
    return (await operation()).data
  } catch (error) {
    if (signal.aborted) throw error
    if (error instanceof TypeError) {
      throw new PointCloudRequestError(NETWORK_ERROR_MESSAGE, true)
    }
    throw new PointCloudRequestError(getApiErrorMessage(error) ?? UNEXPECTED_ERROR_MESSAGE)
  }
}

export function uploadPointCloud(file: File, signal: AbortSignal): Promise<PointCloud> {
  return request(
    async () =>
      uploadPointCloudRequest({
        client,
        body: { file },
        signal,
        throwOnError: true,
      }),
    signal,
  )
}

export function startConversion(pointCloudId: string, signal: AbortSignal): Promise<Job> {
  return request(
    async () =>
      convertPointCloudRequest({
        client,
        path: { id: pointCloudId },
        signal,
        throwOnError: true,
      }),
    signal,
  )
}

export function getJob(jobId: string, signal: AbortSignal): Promise<Job> {
  return request(
    async () =>
      getJobRequest({
        client,
        path: { id: jobId },
        signal,
        throwOnError: true,
      }),
    signal,
  )
}

export function waitForNextJobPoll(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('The request was aborted', 'AbortError'))
      return
    }

    const onAbort = () => {
      clearTimeout(timeout)
      reject(new DOMException('The request was aborted', 'AbortError'))
    }
    const timeout = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, 1000)
    signal.addEventListener('abort', onAbort, { once: true })
  })
}
