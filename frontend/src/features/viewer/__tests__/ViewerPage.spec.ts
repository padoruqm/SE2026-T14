import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ViewerPage from '../ViewerPage.vue'
import { checkWebGL } from '../checkWebGL'
import { mountPotreeViewer, type PotreeViewerHandle } from '../potreeViewer'

vi.mock('../checkWebGL', () => ({ checkWebGL: vi.fn<() => boolean>() }))
vi.mock('../potreeViewer', () => ({
  mountPotreeViewer: vi.fn<(element: HTMLElement, url: string) => Promise<PotreeViewerHandle>>(),
}))

const fetchMock = vi.fn<typeof fetch>()

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function pointCloud(status = 'ready') {
  return {
    id: 'pc_1',
    filename: 'survey.las',
    status,
    metadata: { pointCount: 10, bounds: null, crs: null },
  }
}

function handle(): PotreeViewerHandle {
  return {
    dispose: vi.fn<() => void>(),
    resetView: vi.fn<() => void>(),
    setPointSize: vi.fn<(size: number) => void>(),
    setColorMode: vi.fn<(mode: 'rgb' | 'elevation' | 'intensity') => void>(),
  } as PotreeViewerHandle
}

async function mountPage() {
  const wrapper = mount(ViewerPage, {
    props: { id: 'pc_1' },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.mocked(checkWebGL).mockReturnValue(true)
  vi.mocked(mountPotreeViewer).mockReset()
  vi.mocked(mountPotreeViewer).mockResolvedValue(handle())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ViewerPage states', () => {
  it('explains that WebGL is missing and does not start the viewer', async () => {
    vi.mocked(checkWebGL).mockReturnValue(false)
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, pointCloud())))

    const wrapper = await mountPage()

    expect(wrapper.get('[role="alert"]').text()).toContain('WebGL')
    expect(wrapper.get('a').attributes('href')).toBe('/upload')
    expect(mountPotreeViewer).not.toHaveBeenCalled()
  })

  it('shows a loading state while the point cloud is being fetched', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))

    const wrapper = await mountPage()

    expect(wrapper.get('[role="status"]').text()).toBe('Loading point cloud…')
    expect(mountPotreeViewer).not.toHaveBeenCalled()
  })

  it('shows a not-found page with a link to upload for an unknown id', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'x', requestId: 'r' } }),
      ),
    )

    const wrapper = await mountPage()

    expect(wrapper.get('[role="alert"]').text()).toContain('Point cloud not found')
    expect(wrapper.get('a').attributes('href')).toBe('/upload')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(mountPotreeViewer).not.toHaveBeenCalled()
  })

  it('shows a network error and retries the request', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, pointCloud())))

    const wrapper = await mountPage()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not reach the server')

    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(mountPotreeViewer).toHaveBeenCalledOnce()
  })

  it('shows a failure message when the point cloud failed processing', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, pointCloud('failed'))))

    const wrapper = await mountPage()

    expect(wrapper.get('[role="alert"]').text()).toContain('Processing failed')
    expect(wrapper.get('a').attributes('href')).toBe('/upload')
    expect(mountPotreeViewer).not.toHaveBeenCalled()
  })

  it('mounts the viewer for a ready point cloud', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, pointCloud())))

    const wrapper = await mountPage()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(mountPotreeViewer).toHaveBeenCalledOnce()
  })
})
