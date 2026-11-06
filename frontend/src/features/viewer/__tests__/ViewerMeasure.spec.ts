import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import type { Vec3 } from '@/features/measure'

import ViewerPage from '../ViewerPage.vue'
import { mountPotreeViewer, type PotreeViewerHandle } from '../potreeViewer'

vi.mock('../potreeViewer', () => ({
  mountPotreeViewer: vi.fn<() => Promise<unknown>>(),
}))

const fetchMock = vi.fn<typeof fetch>()

const first = { x: 500000, y: 2000000, z: 100 }
const second = { x: 500003, y: 2000004, z: 112 }

function fakeHandle() {
  let onPick: (point: Vec3) => void = () => {}
  let onUpdate: () => void = () => {}
  const stopPicking = vi.fn<() => void>()
  const stopUpdates = vi.fn<() => void>()
  const handle = {
    setPointSize: vi.fn<(size: number) => void>(),
    setColorMode: vi.fn<(mode: string) => void>(),
    resetView: vi.fn<() => void>(),
    dispose: vi.fn<() => void>(),
    enableMeasure: vi.fn<(callback: (point: Vec3) => void) => () => void>((callback) => {
      onPick = callback
      return stopPicking
    }),
    project: vi.fn<(point: Vec3) => { x: number; y: number; visible: boolean }>((point) => ({
      x: point.x - 499900,
      y: point.y - 1999900,
      visible: true,
    })),
    onUpdate: vi.fn<(listener: () => void) => () => void>((listener) => {
      onUpdate = listener
      return stopUpdates
    }),
  }
  return {
    handle: handle as unknown as PotreeViewerHandle & typeof handle,
    pick: (point: Vec3) => onPick(point),
    update: () => onUpdate(),
    stopPicking,
    stopUpdates,
  }
}

function pointCloud(crs: string | null) {
  return {
    id: 'pc_1',
    filename: 'survey.laz',
    status: 'ready',
    metadata: { pointCount: 5, bounds: null, crs },
    viewerUrl: null,
    sourceId: null,
  }
}

async function mountPage(crs: string | null = 'EPSG:32648') {
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify(pointCloud(crs)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  const fake = fakeHandle()
  vi.mocked(mountPotreeViewer).mockResolvedValue(fake.handle)
  const wrapper = mount(ViewerPage, { props: { id: 'pc_1' } })
  await flushPromises()
  return { wrapper, ...fake }
}

function button(wrapper: Awaited<ReturnType<typeof mountPage>>['wrapper'], label: string) {
  const found = wrapper.findAll('button').find((b) => b.text() === label)
  if (!found) throw new Error(`no "${label}" button`)
  return found
}

async function startMeasuring(page: Awaited<ReturnType<typeof mountPage>>) {
  await button(page.wrapper, 'Measure').trigger('click')
  await flushPromises()
}

function results(page: Awaited<ReturnType<typeof mountPage>>) {
  return page.wrapper.get('.measure-panel [role="status"]').text()
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.mocked(mountPotreeViewer).mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('measuring in the viewer', () => {
  it('does not pick anything until Measure is switched on', async () => {
    const page = await mountPage()

    expect(page.handle.enableMeasure).not.toHaveBeenCalled()
  })

  it('shows the coordinates of one picked point and marks it on the view', async () => {
    const page = await mountPage()
    await startMeasuring(page)

    page.pick({ x: 500001.25, y: 2000002.5, z: 100.75 })
    await flushPromises()

    expect(results(page)).toContain('500001.250')
    expect(results(page)).toContain('2000002.500')
    expect(results(page)).toContain('100.750')
    expect(page.wrapper.findAll('.measure-marker')).toHaveLength(1)
    expect(page.wrapper.find('.measure-line').exists()).toBe(false)
  })

  it('shows the distance of two picked points, with a line and a label', async () => {
    const page = await mountPage()
    await startMeasuring(page)

    page.pick(first)
    page.pick(second)
    await flushPromises()

    expect(results(page)).toContain('13.000 m')
    expect(results(page)).toContain('5.000 m')
    expect(results(page)).toContain('12.000 m')
    expect(page.wrapper.findAll('.measure-marker')).toHaveLength(2)
    expect(page.wrapper.find('.measure-line').exists()).toBe(true)
    expect(page.wrapper.get('.measure-label').text()).toBe('13.000 m')
  })

  it('starts a new measurement on the third pick', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    page.pick(second)

    page.pick({ x: 500010, y: 2000010, z: 105 })
    await flushPromises()

    expect(results(page)).toContain('500010.000')
    expect(results(page)).not.toContain('Distance')
    expect(page.wrapper.findAll('.measure-marker')).toHaveLength(1)
  })

  it('asks before deleting, and keeps everything if the answer is Keep', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    page.pick(second)
    await flushPromises()

    await button(page.wrapper, 'Clear measurement').trigger('click')

    expect(page.wrapper.text()).toContain('Delete this measurement?')
    expect(results(page)).toContain('13.000 m')

    await button(page.wrapper, 'Keep').trigger('click')

    expect(page.wrapper.text()).not.toContain('Delete this measurement?')
    expect(results(page)).toContain('13.000 m')
    expect(page.wrapper.findAll('.measure-marker')).toHaveLength(2)
  })

  it('removes the measurement and its markers once deletion is confirmed', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    page.pick(second)
    await flushPromises()

    await button(page.wrapper, 'Clear measurement').trigger('click')
    await button(page.wrapper, 'Delete').trigger('click')

    expect(results(page)).toBe('')
    expect(page.wrapper.findAll('.measure-marker')).toHaveLength(0)
    expect(page.wrapper.find('.measure-line').exists()).toBe(false)
  })

  it('ignores clicks in the viewer while the delete question is open', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    await flushPromises()
    await button(page.wrapper, 'Clear measurement').trigger('click')

    page.pick(second)
    await flushPromises()

    await button(page.wrapper, 'Keep').trigger('click')
    expect(page.wrapper.findAll('.measure-marker')).toHaveLength(1)
  })

  it('never changes the data: it only ever reads the point cloud metadata', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    page.pick(second)
    await flushPromises()
    await button(page.wrapper, 'Clear measurement').trigger('click')
    await button(page.wrapper, 'Delete').trigger('click')
    await flushPromises()

    const methods = fetchMock.mock.calls.map((call) => (call[0] as Request).method)
    expect(new Set(methods)).toEqual(new Set(['GET']))
  })

  it('stops picking when Measure is switched off but keeps the measurement shown', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    page.pick(second)
    await flushPromises()

    await button(page.wrapper, 'Stop measuring').trigger('click')
    await flushPromises()

    expect(page.stopPicking).toHaveBeenCalledOnce()
    expect(results(page)).toContain('13.000 m')
  })

  it('places the markers again after the view moves', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    await flushPromises()
    const before = page.handle.project.mock.calls.length

    page.update()
    await flushPromises()

    expect(page.handle.onUpdate).toHaveBeenCalledOnce()
    expect(page.handle.project.mock.calls.length).toBeGreaterThan(before)
  })

  it('does not watch the view while there is nothing to draw', async () => {
    const page = await mountPage()
    await startMeasuring(page)

    expect(page.handle.onUpdate).not.toHaveBeenCalled()
  })

  it('releases picking and view updates when the page goes away', async () => {
    const page = await mountPage()
    await startMeasuring(page)
    page.pick(first)
    await flushPromises()

    page.wrapper.unmount()

    expect(page.stopPicking).toHaveBeenCalled()
    expect(page.stopUpdates).toHaveBeenCalled()
    expect(page.handle.dispose).toHaveBeenCalledOnce()
  })

  it('says units when the CRS is not known', async () => {
    const page = await mountPage(null)
    await startMeasuring(page)

    page.pick(first)
    page.pick(second)
    await flushPromises()

    expect(results(page)).toContain('13.000 units')
  })

  it('refuses a distance, and a label, for a geographic CRS', async () => {
    const page = await mountPage('EPSG:4326')
    await startMeasuring(page)

    page.pick({ x: 105.1, y: 21.2, z: 10 })
    page.pick({ x: 105.2, y: 21.3, z: 10 })
    await flushPromises()

    expect(page.wrapper.text()).toContain('angular coordinates')
    expect(page.wrapper.text()).not.toContain('Distance')
    expect(page.wrapper.find('.measure-label').exists()).toBe(false)
  })
})
