import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ViewerCanvas from '../ViewerCanvas.vue'
import { mountPotreeViewer, type PotreeViewerHandle } from '../potreeViewer'

vi.mock('../potreeViewer', () => ({
  mountPotreeViewer: vi.fn<(element: HTMLElement, url: string) => Promise<PotreeViewerHandle>>(),
}))

function handle() {
  return {
    dispose: vi.fn<() => void>(),
    resetView: vi.fn<() => void>(),
    setPointSize: vi.fn<(size: number) => void>(),
    setColorMode: vi.fn<(mode: 'rgb' | 'elevation' | 'intensity') => void>(),
  }
}

function mountCanvas() {
  return mount(ViewerCanvas, { props: { url: '/m.json', pointSize: 2, colorMode: 'rgb' } })
}

beforeEach(() => {
  vi.mocked(mountPotreeViewer).mockReset()
})

describe('ViewerCanvas', () => {
  it('shows an error with retry instead of an empty canvas when loading fails', async () => {
    vi.mocked(mountPotreeViewer).mockRejectedValue(new Error('404'))

    const wrapper = mountCanvas()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('could not be loaded')
    expect(wrapper.get('[role="alert"] button').text()).toBe('Try again')
  })

  it('retries loading and clears the error on success', async () => {
    const loaded = handle()
    vi.mocked(mountPotreeViewer).mockRejectedValueOnce(new Error('404'))
    vi.mocked(mountPotreeViewer).mockResolvedValueOnce(loaded as unknown as PotreeViewerHandle)

    const wrapper = mountCanvas()
    await flushPromises()
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(mountPotreeViewer).toHaveBeenCalledTimes(2)
    expect(loaded.setPointSize).toHaveBeenCalledWith(2)
  })

  it('disposes the viewer on unmount', async () => {
    const loaded = handle()
    vi.mocked(mountPotreeViewer).mockResolvedValue(loaded as unknown as PotreeViewerHandle)

    const wrapper = mountCanvas()
    await flushPromises()
    wrapper.unmount()

    expect(loaded.dispose).toHaveBeenCalledOnce()
  })
})
