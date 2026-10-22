import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import MetadataPanel from '../MetadataPanel.vue'

const fetchMock = vi.fn<typeof fetch>()

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function pointCloud(metadata: unknown) {
  return { id: 'pc_1', filename: 'survey.laz', status: 'ready', metadata }
}

const fullMetadata = {
  pointCount: 1250000,
  bounds: { minX: 100, minY: 200, minZ: -1.5, maxX: 180.5, maxY: 260.25, maxZ: 42.7 },
  crs: 'EPSG:32648',
}

async function mountPanel(response: Response | Promise<Response>) {
  fetchMock.mockReturnValue(Promise.resolve(response))
  const wrapper = mount(MetadataPanel, { props: { id: 'pc_1' } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('MetadataPanel', () => {
  it('shows a loading state while the request is pending', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))

    const wrapper = mount(MetadataPanel, { props: { id: 'pc_1' } })
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toBe('Loading metadata…')
    expect(wrapper.get('section').attributes('aria-busy')).toBe('true')
  })

  it('shows the file, point count, CRS and bounds', async () => {
    const wrapper = await mountPanel(jsonResponse(200, pointCloud(fullMetadata)))

    expect(wrapper.get('section').attributes('aria-busy')).toBe('false')
    const summary = wrapper.get('dl').text()
    expect(summary).toContain('survey.laz')
    expect(summary).toContain('1,250,000')
    expect(summary).toContain('EPSG:32648')

    const rows = wrapper
      .findAll('tbody tr')
      .map((row) => row.findAll('th, td').map((cell) => cell.text()))
    expect(rows).toEqual([
      ['X', '100.000', '180.500', '80.500'],
      ['Y', '200.000', '260.250', '60.250'],
      ['Z', '-1.500', '42.700', '44.200'],
    ])
  })

  it('marks missing fields as not available when others are present', async () => {
    const wrapper = await mountPanel(
      jsonResponse(200, pointCloud({ pointCount: 42, bounds: null, crs: null })),
    )

    expect(wrapper.get('dl').text()).toContain('42')
    expect(wrapper.get('dl').text()).toContain('Not available')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).toContain('Bounds: Not available')
  })

  it('shows an empty state when the point cloud has no metadata yet', async () => {
    const wrapper = await mountPanel(
      jsonResponse(200, pointCloud({ pointCount: null, bounds: null, crs: null })),
    )

    expect(wrapper.get('[role="status"]').text()).toBe(
      'No metadata is available for this point cloud yet.',
    )
    expect(wrapper.find('dl').exists()).toBe(false)
  })

  it('shows the server error and retries', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, {
        error: { code: 'NOT_FOUND', message: 'Not Found', requestId: 'req_1', details: {} },
      }),
    )
    fetchMock.mockResolvedValueOnce(jsonResponse(200, pointCloud(fullMetadata)))
    const wrapper = mount(MetadataPanel, { props: { id: 'pc_1' } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Not Found')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('dl').text()).toContain('1,250,000')
  })

  it('shows a message when the server cannot be reached', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const wrapper = mount(MetadataPanel, { props: { id: 'pc_1' } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Could not reach the server')
  })

  it('reloads when the id prop changes', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, pointCloud(fullMetadata)))
    const wrapper = mount(MetadataPanel, { props: { id: 'pc_1' } })
    await flushPromises()

    await wrapper.setProps({ id: 'pc_2' })
    await flushPromises()

    const urls = fetchMock.mock.calls.map((call) => new URL((call[0] as Request).url).pathname)
    expect(urls).toEqual(['/api/pointcloud/pc_1', '/api/pointcloud/pc_2'])
  })
})
