import { apiBaseUrl } from '@/shared/config'

// TODO(#7): replace with the types from the generated OpenAPI client.
export interface PointCloud {
  id: string
  filename: string
  status: string
}

interface ErrorResponse {
  error?: { code?: string; message?: string }
}

export class UploadError extends Error {}

const NETWORK_ERROR_MESSAGE = 'Could not reach the server. Check your connection and try again.'
const UNEXPECTED_ERROR_MESSAGE = 'Upload failed. Please try again.'

export async function uploadPointCloud(file: File, signal?: AbortSignal): Promise<PointCloud> {
  const body = new FormData()
  body.append('file', file)

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}/api/upload`, { method: 'POST', body, signal })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new UploadError(NETWORK_ERROR_MESSAGE)
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorResponse
    throw new UploadError(payload.error?.message ?? UNEXPECTED_ERROR_MESSAGE)
  }
  return (await response.json()) as PointCloud
}
