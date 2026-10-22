import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import App from '../App.vue'
import { createAppRouter } from '../router'

async function mountAt(path: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router] } })
  return { router, wrapper }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('app routing', () => {
  it('redirects the root path to the upload page', async () => {
    const { router, wrapper } = await mountAt('/')

    expect(router.currentRoute.value.fullPath).toBe('/upload')
    expect(wrapper.text()).toContain('Upload point cloud')
  })

  it('renders the viewer placeholder with the dataset id', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockReturnValue(new Promise(() => {})))
    const { wrapper } = await mountAt('/viewer/abc')

    expect(wrapper.text()).toContain('Viewer')
    expect(wrapper.text()).toContain('abc')
  })

  it('requests the metadata of the dataset shown in the viewer', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockReturnValue(new Promise(() => {}))
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountAt('/viewer/abc')
    await flushPromises()

    expect(wrapper.text()).toContain('Loading metadata')
    expect(new URL((fetchMock.mock.calls[0]![0] as Request).url).pathname).toBe(
      '/api/pointcloud/abc',
    )
  })
})
