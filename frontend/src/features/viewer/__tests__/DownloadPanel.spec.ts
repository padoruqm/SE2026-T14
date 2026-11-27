import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import DownloadPanel from '../DownloadPanel.vue'

const fetchMock = vi.fn<typeof fetch>()
const createObjectURL = vi.fn<(blob: Blob) => string>()
const revokeObjectURL = vi.fn<(url: string) => void>()

class DownloadTestURL extends URL {
  static override createObjectURL = createObjectURL
  static override revokeObjectURL = revokeObjectURL
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function errorResponse(status: number, code: string) {
  return jsonResponse(status, {
    error: { code, message: '/secret/server/path', requestId: 'req_1', details: {} },
  })
}

function render(ready = true) {
  return mount(DownloadPanel, {
    props: { id: 'pc_1', filename: 'survey.laz', ready },
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  createObjectURL.mockReset()
  createObjectURL.mockReturnValue('blob:download')
  revokeObjectURL.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', DownloadTestURL)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DownloadPanel', () => {
  it('disables download until the point cloud is ready', async () => {
    const wrapper = render(false)

    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Download is available once processing is complete.')
    await wrapper.get('button').trigger('click')

    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('downloads the file with its recorded filename and reports success after starting', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(new Blob(['LAS bytes']), {
        status: 200,
        headers: { 'Content-Type': 'application/octet-stream' },
      }),
    )
    let clickedFilename: string | undefined
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clickedFilename = this.download
    })
    const wrapper = render()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(new URL(request.url).pathname).toBe('/api/pointcloud/pc_1/download')
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(clickedFilename).toBe('survey.laz')
    expect(wrapper.get('[role="status"]').text()).toBe('Download started.')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it.each([
    [409, 'CONFLICT', 'not ready to download yet'],
    [404, 'NOT_FOUND', 'was not found'],
    [410, 'GONE', 'no longer available'],
    [500, 'INTERNAL_ERROR', 'Could not download this point cloud'],
  ])('does not report success when the API returns %i %s', async (status, code, message) => {
    fetchMock.mockResolvedValueOnce(errorResponse(status, code))
    const wrapper = render()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(createObjectURL).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain(message)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('does not report success when the download request fails on the network', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const wrapper = render()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(createObjectURL).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not reach the server')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('does not report success when the browser cannot start the download', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(new Blob(['LAS bytes']), {
        status: 200,
        headers: { 'Content-Type': 'application/octet-stream' },
      }),
    )
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('Download blocked')
    })
    const wrapper = render()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Could not start the download')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })
})
