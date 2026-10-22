import { onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { getPointCloud, type PointCloudDetail } from '@/api/generated'
import { apiBaseUrl } from '@/shared/config'

export type MetadataState = 'loading' | 'ready' | 'empty' | 'error'

const NETWORK_ERROR_MESSAGE = 'Could not reach the server. Check your connection and try again.'
const UNEXPECTED_ERROR_MESSAGE = 'The server returned an unexpected response. Please try again.'

function serverMessage(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('error' in error)) return null
  const body = error.error
  if (typeof body !== 'object' || body === null || !('message' in body)) return null
  return typeof body.message === 'string' ? body.message : null
}

function errorMessage(error: unknown): string {
  if (error instanceof TypeError) return NETWORK_ERROR_MESSAGE
  return serverMessage(error) ?? UNEXPECTED_ERROR_MESSAGE
}

function hasNoMetadata({ metadata }: PointCloudDetail): boolean {
  return metadata.pointCount === null && metadata.bounds === null && metadata.crs === null
}

export function usePointCloudMetadata(id: MaybeRefOrGetter<string>) {
  const state = ref<MetadataState>('loading')
  const pointCloud = ref<PointCloudDetail | null>(null)
  const error = ref<string | null>(null)

  let controller: AbortController | null = null

  async function load(): Promise<void> {
    controller?.abort()
    const current = new AbortController()
    controller = current
    state.value = 'loading'
    pointCloud.value = null
    error.value = null

    try {
      const result = await getPointCloud({
        baseUrl: apiBaseUrl,
        path: { id: toValue(id) },
        signal: current.signal,
      })
      if (current.signal.aborted) return

      if (result.data === undefined) {
        fail(errorMessage(result.error))
        return
      }
      pointCloud.value = result.data
      state.value = hasNoMetadata(result.data) ? 'empty' : 'ready'
    } catch (caught) {
      if (current.signal.aborted) return
      fail(errorMessage(caught))
    }
  }

  function fail(message: string): void {
    state.value = 'error'
    error.value = message
  }

  watch(() => toValue(id), load, { immediate: true })

  onScopeDispose(() => controller?.abort())

  return { state, pointCloud, error, reload: load }
}
