import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

import { useCropRequest } from '../useCropRequest'

const fetchMock = vi.fn<typeof fetch>()

const BOUNDS = {
  minX: 500010,
  minY: 2000005,
  minZ: 100,
  maxX: 500030,
  maxY: 2000045,
  maxZ: 106,
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function job(state: string, extra: Record<string, unknown> = {}) {
  return {
    id: 'job_1',
    type: 'crop',
    state,
    progress: null,
    resultId: null,
    error: null,
    ...extra,
  }
}

function apiError(status: number, code: string, message = '/secret/server/path') {
  return json(status, { error: { code, message, requestId: 'req_1', details: {} } })
}

function setup(id = ref('pc_1')) {
  const scope = effectScope()
  const crop = scope.run(() => useCropRequest(id))!
  return { crop, scope, id }
}

function requests() {
  return fetchMock.mock.calls.map((call) => call[0] as Request)
}

beforeEach(() => {
  vi.useFakeTimers()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useCropRequest', () => {
  it('posts the bounds and format to the crop endpoint', async () => {
    fetchMock.mockResolvedValueOnce(json(202, job('succeeded', { resultId: 'pc_2' })))
    const { crop } = setup()

    await crop.submit(BOUNDS, 'las')

    const [request] = requests()
    expect(request?.method).toBe('POST')
    expect(new URL(request!.url).pathname).toBe('/api/pointcloud/pc_1/crop')
    expect(await request!.json()).toEqual({ bounds: BOUNDS, outputFormat: 'las' })
  })

  it('follows the job and ends with the new point cloud', async () => {
    fetchMock
      .mockResolvedValueOnce(json(202, job('queued')))
      .mockResolvedValueOnce(json(200, job('running', { progress: 40 })))
      .mockResolvedValueOnce(json(200, job('succeeded', { progress: 100, resultId: 'pc_2' })))
    const { crop } = setup()

    const done = crop.submit(BOUNDS, 'laz')
    await vi.advanceTimersByTimeAsync(0)
    expect(crop.state.value).toBe('queued')

    await vi.advanceTimersByTimeAsync(1000)
    expect(crop.state.value).toBe('running')
    expect(crop.progress.value).toBe(40)

    await vi.advanceTimersByTimeAsync(1000)
    await done
    expect(crop.state.value).toBe('succeeded')
    expect(crop.resultId.value).toBe('pc_2')
    expect(crop.error.value).toBeNull()
    expect(new URL(requests()[1]!.url).pathname).toBe('/api/job/job_1')
  })

  it('ignores a second submit while a crop is running', async () => {
    fetchMock
      .mockResolvedValueOnce(json(202, job('running')))
      .mockResolvedValue(json(200, job('running')))
    const { crop, scope } = setup()

    void crop.submit(BOUNDS, 'laz')
    await vi.advanceTimersByTimeAsync(0)
    await crop.submit({ ...BOUNDS, maxX: 500020 }, 'las')

    const posts = requests().filter((r) => r.method === 'POST')
    expect(posts).toHaveLength(1)
    scope.stop()
  })

  it.each([
    [409, 'CONFLICT', 'not ready to crop yet', false],
    [404, 'NOT_FOUND', 'was not found', false],
    [410, 'GONE', 'no longer available', false],
    [422, 'VALIDATION_ERROR', 'crop region is not valid', false],
    [500, 'INTERNAL_ERROR', 'could not be started', true],
  ])('explains a %i %s from the server', async (status, code, text, canRetry) => {
    fetchMock.mockResolvedValueOnce(apiError(status, code))
    const { crop } = setup()

    await crop.submit(BOUNDS, 'laz')

    expect(crop.state.value).toBe('failed')
    expect(crop.error.value).toContain(text)
    expect(crop.retryable.value).toBe(canRetry)
  })

  it('never shows the server error text', async () => {
    fetchMock.mockResolvedValueOnce(apiError(500, 'INTERNAL_ERROR', '/var/lib/data/crash.py'))
    const { crop } = setup()

    await crop.submit(BOUNDS, 'laz')

    expect(crop.error.value).not.toContain('/var/lib')
  })

  it('reports a network failure as retryable', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const { crop } = setup()

    await crop.submit(BOUNDS, 'laz')

    expect(crop.error.value).toContain('Could not reach the server')
    expect(crop.retryable.value).toBe(true)
  })

  it('explains a job that failed, without its server text', async () => {
    fetchMock
      .mockResolvedValueOnce(json(202, job('running')))
      .mockResolvedValueOnce(
        json(
          200,
          job('failed', { error: { code: 'INVALID_POINT_CLOUD', message: 'pdal: /tmp/x.las' } }),
        ),
      )
    const { crop } = setup()

    const done = crop.submit(BOUNDS, 'laz')
    await vi.advanceTimersByTimeAsync(1000)
    await done

    expect(crop.state.value).toBe('failed')
    expect(crop.error.value).toBe('This point cloud could not be cropped.')
    expect(crop.resultId.value).toBeNull()
  })

  it('uses a general message for a job failure it does not know', async () => {
    fetchMock
      .mockResolvedValueOnce(json(202, job('running')))
      .mockResolvedValueOnce(
        json(200, job('failed', { error: { code: 'INTERNAL_ERROR', message: 'x' } })),
      )
    const { crop } = setup()

    const done = crop.submit(BOUNDS, 'laz')
    await vi.advanceTimersByTimeAsync(1000)
    await done

    expect(crop.error.value).toBe('The crop failed. Please try again.')
    expect(crop.retryable.value).toBe(true)
  })

  it('retries with the same bounds and format', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(json(202, job('succeeded', { resultId: 'pc_2' })))
    const { crop } = setup()
    await crop.submit(BOUNDS, 'las')

    await crop.retry()

    expect(crop.state.value).toBe('succeeded')
    expect(await requests()[1]!.json()).toEqual({ bounds: BOUNDS, outputFormat: 'las' })
  })

  it('does not retry when nothing has failed', async () => {
    const { crop } = setup()

    await crop.retry()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('stops polling when its scope is disposed', async () => {
    fetchMock
      .mockResolvedValueOnce(json(202, job('running')))
      .mockResolvedValue(json(200, job('running')))
    const { crop, scope } = setup()
    void crop.submit(BOUNDS, 'laz')
    await vi.advanceTimersByTimeAsync(2500)
    const calls = fetchMock.mock.calls.length

    scope.stop()
    await vi.advanceTimersByTimeAsync(10_000)

    expect(fetchMock.mock.calls.length).toBe(calls)
  })

  it('starts from scratch when the point cloud changes', async () => {
    fetchMock.mockResolvedValueOnce(json(202, job('succeeded', { resultId: 'pc_2' })))
    const { crop, id } = setup()
    await crop.submit(BOUNDS, 'laz')
    expect(crop.resultId.value).toBe('pc_2')

    id.value = 'pc_other'
    await vi.advanceTimersByTimeAsync(0)

    expect(crop.state.value).toBe('idle')
    expect(crop.resultId.value).toBeNull()
  })
})
