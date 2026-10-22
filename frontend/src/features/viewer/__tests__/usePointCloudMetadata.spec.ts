import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

import { usePointCloudMetadata } from '../usePointCloudMetadata'

const fetchMock = vi.fn<typeof fetch>()

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const full = {
  id: 'pc_1',
  filename: 'survey.laz',
  status: 'ready',
  metadata: {
    pointCount: 1250000,
    bounds: { minX: 1, minY: 2, minZ: 3, maxX: 4, maxY: 5, maxZ: 6 },
    crs: 'EPSG:32648',
  },
  viewerUrl: null,
  sourceId: null,
}

function setup(id = ref('pc_1')) {
  let result!: ReturnType<typeof usePointCloudMetadata>
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePointCloudMetadata(id)
        return () => h('div')
      },
    }),
  )
  return { wrapper, id, result }
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('usePointCloudMetadata', () => {
  it('starts in the loading state and requests the point cloud', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('loading')
    const request = fetchMock.mock.calls[0]![0] as Request
    expect(request.method).toBe('GET')
    expect(new URL(request.url).pathname).toBe('/api/pointcloud/pc_1')
  })

  it('becomes ready with the point cloud when metadata is present', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, full))

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('ready')
    expect(result.pointCloud.value?.metadata.crs).toBe('EPSG:32648')
  })

  it('becomes empty when the server has no metadata yet', async () => {
    const noMetadata = { ...full, metadata: { pointCount: null, bounds: null, crs: null } }
    fetchMock.mockResolvedValue(jsonResponse(200, noMetadata))

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('empty')
  })

  it('stays ready when only some metadata is present', async () => {
    const partial = { ...full, metadata: { pointCount: 5, bounds: null, crs: null } }
    fetchMock.mockResolvedValue(jsonResponse(200, partial))

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('ready')
  })

  it('reports the server error message', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(404, {
        error: { code: 'NOT_FOUND', message: 'Not Found', requestId: 'req_1', details: {} },
      }),
    )

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('error')
    expect(result.error.value).toBe('Not Found')
  })

  it('falls back to a generic message for non-JSON error bodies', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }))

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('error')
    expect(result.error.value).toBe('The server returned an unexpected response. Please try again.')
  })

  it('reports a network failure', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const { result } = setup()
    await flushPromises()

    expect(result.state.value).toBe('error')
    expect(result.error.value).toContain('Could not reach the server')
  })

  it('reloads after an error', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, full))
    const { result } = setup()
    await flushPromises()

    void result.reload()
    await flushPromises()

    expect(result.state.value).toBe('ready')
    expect(result.error.value).toBeNull()
  })

  it('loads again when the id changes and ignores the stale response', async () => {
    let resolveFirst!: (response: Response) => void
    fetchMock.mockReturnValueOnce(new Promise((resolve) => (resolveFirst = resolve)))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ...full, id: 'pc_2' }))
    const { result, id } = setup()

    id.value = 'pc_2'
    await flushPromises()
    resolveFirst(jsonResponse(200, { ...full, id: 'pc_1' }))
    await flushPromises()

    expect(result.pointCloud.value?.id).toBe('pc_2')
  })

  it('aborts the request when unmounted', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))
    const { wrapper } = setup()
    await flushPromises()

    wrapper.unmount()

    const request = fetchMock.mock.calls[0]![0] as Request
    expect(request.signal.aborted).toBe(true)
  })
})
