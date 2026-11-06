import { afterEach, describe, expect, it, vi } from 'vitest'
import { DraftApiError, viewerDraftApi } from '../viewerDraftApi'

afterEach(() => {
  vi.unstubAllGlobals()
})
describe('draft HTTP adapter', () => {
  it('sends the versioned operation contract and forwards cancellation', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          revision: 1,
          state: { pointSize: 2, colorMode: 'rgb' },
        }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const command = {
      expectedRevision: 0,
      operationId: 'edit-1',
      state: { pointSize: 2, colorMode: 'rgb' as const },
    }
    const signal = new AbortController().signal
    expect(await viewerDraftApi.save('pc_alpha', command, signal)).toMatchObject({ revision: 1 })
    expect(fetchMock.mock.calls[0]![0]).toContain('/api/pointcloud/pc_alpha/draft')
    expect(fetchMock.mock.calls[0]![1]).toMatchObject({
      method: 'PUT',
      signal,
      body: JSON.stringify(command),
    })
  })

  it('does not interpret a 409 as a saved draft', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 409 })),
    )
    await expect(
      viewerDraftApi.load('pc_alpha', new AbortController().signal),
    ).rejects.toBeInstanceOf(DraftApiError)
  })

  it.each([
    {},
    { revision: -1, state: { pointSize: 2, colorMode: 'rgb' } },
    { revision: 1, state: { pointSize: 9, colorMode: 'rgb' } },
    { revision: 1, state: { pointSize: 2, colorMode: 'unknown' } },
  ])('rejects an unverified successful payload %#', async (body) => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(body))),
    )
    await expect(viewerDraftApi.load('pc_alpha', new AbortController().signal)).rejects.toThrow(
      'Invalid draft response',
    )
  })
})
