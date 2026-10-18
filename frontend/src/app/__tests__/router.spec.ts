import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
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

describe('app routing', () => {
  it('redirects the root path to the upload page', async () => {
    const { router, wrapper } = await mountAt('/')

    expect(router.currentRoute.value.fullPath).toBe('/upload')
    expect(wrapper.text()).toContain('Upload point cloud')
  })

  it('renders the viewer placeholder with the dataset id', async () => {
    const { wrapper } = await mountAt('/viewer/abc')

    expect(wrapper.text()).toContain('Viewer')
    expect(wrapper.text()).toContain('abc')
  })
})
