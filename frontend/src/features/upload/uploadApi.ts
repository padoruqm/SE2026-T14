import { apiBaseUrl } from '@/shared/config'
import type { Job, PointCloud } from '@/api/generated/types.gen'

export class PointCloudRequestError extends Error {}

const NETWORK_ERROR_MESSAGE = 'Could not reach the server. Check your connection and try again.'
const UNEXPECTED_ERROR_MESSAGE = 'The server returned an unexpected response. Please try again.'
const JOB_STATES = ['queued', 'running', 'succeeded', 'failed', 'cancelled']
const JOB_TYPES = ['convert', 'crop', 'filter']
const ERROR_CODES = [
  'BAD_REQUEST',
  'VALIDATION_ERROR',
  'FILE_TOO_LARGE',
  'UNSUPPORTED_FILE_TYPE',
  'INVALID_POINT_CLOUD',
  'NOT_FOUND',
  'METHOD_NOT_ALLOWED',
  'CONFLICT',
  'INTERNAL_ERROR',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isPointCloud(value: unknown): value is PointCloud {
  if (!isRecord(value) || !isRecord(value.metadata)) return false

  const { pointCount, bounds, crs } = value.metadata
  return (
    typeof value.id === 'string' &&
    typeof value.filename === 'string' &&
    typeof value.status === 'string' &&
    ['uploaded', 'converting', 'ready', 'failed'].includes(value.status) &&
    (pointCount === null || typeof pointCount === 'number') &&
    (bounds === null || isRecord(bounds)) &&
    (crs === null || typeof crs === 'string')
  )
}

function isJob(value: unknown): value is Job {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.type === 'string' &&
    JOB_TYPES.includes(value.type) &&
    typeof value.state === 'string' &&
    JOB_STATES.includes(value.state) &&
    (value.progress === null ||
      (typeof value.progress === 'number' && value.progress >= 0 && value.progress <= 100)) &&
    (value.resultId === null || typeof value.resultId === 'string') &&
    (value.error === null ||
      (isRecord(value.error) &&
        typeof value.error.code === 'string' &&
        ERROR_CODES.includes(value.error.code) &&
        typeof value.error.message === 'string'))
  )
}

async function requestJson<T>(
  url: string,
  init: RequestInit,
  isExpectedResponse: (value: unknown) => value is T,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new PointCloudRequestError(NETWORK_ERROR_MESSAGE)
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const message =
      isRecord(payload) &&
      isRecord(payload.error) &&
      typeof payload.error.message === 'string'
        ? payload.error.message
        : UNEXPECTED_ERROR_MESSAGE
    throw new PointCloudRequestError(message)
  }

  const payload: unknown = await response.json().catch(() => null)
  if (!isExpectedResponse(payload)) {
    throw new PointCloudRequestError(UNEXPECTED_ERROR_MESSAGE)
  }
  return payload
}

export async function uploadPointCloud(file: File, signal?: AbortSignal): Promise<PointCloud> {
  const body = new FormData()
  body.append('file', file)

  return requestJson(
    `${apiBaseUrl}/api/upload`,
    { method: 'POST', body, signal },
    isPointCloud,
  )
}

export async function startConversion(pointCloudId: string, signal: AbortSignal): Promise<Job> {
  return requestJson(
    `${apiBaseUrl}/api/pointcloud/${encodeURIComponent(pointCloudId)}/convert`,
    { method: 'POST', signal },
    isJob,
  )
}

export async function getJob(jobId: string, signal: AbortSignal): Promise<Job> {
  return requestJson(
    `${apiBaseUrl}/api/job/${encodeURIComponent(jobId)}`,
    { method: 'GET', signal },
    isJob,
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
    signal.addEventListener(
      'abort',
      onAbort,
      { once: true },
    )
  })
}
