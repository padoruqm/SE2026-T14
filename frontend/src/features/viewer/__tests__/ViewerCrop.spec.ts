import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import type { Vec3 } from '@/features/measure'

import ViewerPage from '../ViewerPage.vue'
import { mountPotreeViewer, type PotreeViewerHandle } from '../potreeViewer'

vi.mock('../potreeViewer', () => ({
  mountPotreeViewer: vi.fn<() => Promise<unknown>>(),
}))

const fetchMock = vi.fn<typeof fetch>()

const dataset = {
  minX: 500000,
  minY: 2000000,
  minZ: 100,
  maxX: 500100,
  maxY: 2000100,
  maxZ: 110,
}

function fakeHandle() {
  let onPick: (point: Vec3) => void = () => {}
  const stopPicking = vi.fn<() => void>()
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
    onUpdate: vi.fn<(listener: () => void) => () => void>(() => vi.fn<() => void>()),
  }
  return {
    handle: handle as unknown as PotreeViewerHandle & typeof handle,
    pick: (point: Vec3) => onPick(point),
    stopPicking,
  }
}

async function mountPage() {
  fetchMock.mockImplementation(
    async () =>
      new Response(
        JSON.stringify({
          id: 'pc_1',
          filename: 'survey.laz',
          status: 'ready',
          metadata: { pointCount: 5, bounds: dataset, crs: 'EPSG:32648' },
          viewerUrl: null,
          sourceId: null,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
  )
  const fake = fakeHandle()
  vi.mocked(mountPotreeViewer).mockResolvedValue(fake.handle)
  const wrapper = mount(ViewerPage, { props: { id: 'pc_1' } })
  await flushPromises()
  return { wrapper, ...fake }
}

type Page = Awaited<ReturnType<typeof mountPage>>

function button(page: Page, label: string) {
  const found = page.wrapper.findAll('button').find((b) => b.text() === label)
  if (!found) throw new Error(`no "${label}" button`)
  return found
}

async function click(page: Page, label: string) {
  await button(page, label).trigger('click')
  await flushPromises()
}

function inputs(page: Page) {
  return page.wrapper
    .findAll<HTMLInputElement>('.crop-panel input')
    .map((input) => input.element.value)
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.mocked(mountPotreeViewer).mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('selecting a crop region in the viewer', () => {
  it('does not pick anything until Pick region is switched on', async () => {
    const page = await mountPage()
    expect(page.handle.enableMeasure).not.toHaveBeenCalled()
  })

  it('turns two picked corners into world bounds and outlines the box', async () => {
    const page = await mountPage()
    await click(page, 'Pick region')

    page.pick({ x: 500080, y: 2000010, z: 104 })
    page.pick({ x: 500020, y: 2000090, z: 103 })
    await flushPromises()

    // Min X, Max X, Min Y, Max Y, Min Z, Max Z: reversed corners come out ordered.
    expect(inputs(page)).toEqual(['500020', '500080', '2000010', '2000090', '100', '110'])
    expect(page.wrapper.get('.crop-result').text()).toContain('500020, 2000010, 100')
    expect(page.wrapper.findAll('.crop-edge')).toHaveLength(12)
    expect(button(page, 'Pick region').attributes('aria-pressed')).toBe('false')
  })

  it('reports a typed region that is outside the point cloud', async () => {
    const page = await mountPage()
    await click(page, 'Pick region')
    page.pick({ x: 500020, y: 2000010, z: 104 })
    page.pick({ x: 500080, y: 2000090, z: 103 })
    await flushPromises()

    const minX = page.wrapper.findAll('.crop-panel input')[0]!
    const maxX = page.wrapper.findAll('.crop-panel input')[1]!
    await minX.setValue('600000')
    await minX.trigger('change')
    await maxX.setValue('600100')
    await maxX.trigger('change')
    await flushPromises()

    expect(page.wrapper.get('.crop-panel [role="alert"]').text()).toContain('does not overlap')
    expect(page.wrapper.find('.crop-result').exists()).toBe(false)
  })

  it('clears the region and the outline', async () => {
    const page = await mountPage()
    await click(page, 'Pick region')
    page.pick({ x: 500020, y: 2000010, z: 104 })
    page.pick({ x: 500080, y: 2000090, z: 103 })
    await flushPromises()

    await click(page, 'Clear')

    expect(inputs(page)).toEqual(['', '', '', '', '', ''])
    expect(page.wrapper.findAll('.crop-edge')).toHaveLength(0)
  })

  it('sends picks to Crop only, and Measure and Crop are never on together', async () => {
    const page = await mountPage()
    await click(page, 'Measure')
    await click(page, 'Pick region')

    expect(page.wrapper.text()).not.toContain('Stop measuring')
    expect(button(page, 'Measure').attributes('aria-pressed')).toBe('false')

    page.pick({ x: 500020, y: 2000010, z: 104 })
    await flushPromises()
    expect(page.wrapper.find('.measure-marker').exists()).toBe(false)
    expect(page.wrapper.findAll('.crop-marker')).toHaveLength(1)

    await click(page, 'Measure')
    expect(button(page, 'Pick region').attributes('aria-pressed')).toBe('false')
  })

  it('stops listening for clicks when picking is switched off', async () => {
    const page = await mountPage()
    await click(page, 'Pick region')
    await click(page, 'Stop picking')
    expect(page.stopPicking).toHaveBeenCalled()
  })
})
