import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import type { Vec3 } from '@/features/measure'

import ViewerPage from '../ViewerPage.vue'
import { checkWebGL } from '../checkWebGL'
import { mountPotreeViewer, type PotreeViewerHandle } from '../potreeViewer'

vi.mock('../checkWebGL', () => ({ checkWebGL: vi.fn<() => boolean>() }))
vi.mock('../potreeViewer', () => ({
  mountPotreeViewer: vi.fn<() => Promise<unknown>>(),
}))

const dataset = {
  minX: 500000,
  minY: 2000000,
  minZ: 100,
  maxX: 500100,
  maxY: 2000100,
  maxZ: 110,
}

type Reply = { status: number; body: unknown }

const cropped = { minX: 500010, minY: 2000020, minZ: 100, maxX: 500040, maxY: 2000060, maxZ: 110 }

const pointClouds: Record<string, unknown> = {
  pc_1: {
    id: 'pc_1',
    filename: 'survey.laz',
    status: 'ready',
    metadata: { pointCount: 5, bounds: dataset, crs: 'EPSG:32648' },
    viewerUrl: null,
    sourceId: null,
  },
  pc_crop: {
    id: 'pc_crop',
    filename: 'survey-crop.laz',
    status: 'ready',
    metadata: { pointCount: 2, bounds: cropped, crs: 'EPSG:32648' },
    viewerUrl: '/api/pointcloud/pc_crop/viewer/metadata.json',
    sourceId: 'pc_1',
  },
}

/** Answers by method and path; the crop and job replies can be queued per test. */
function server(cropReply: Reply, jobReplies: Reply[] = []) {
  const posts: Array<{ path: string; body: unknown }> = []
  const handler = async (input: RequestInfo | URL) => {
    const request = input as Request
    const path = new URL(request.url).pathname
    const send = ({ status, body }: Reply) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    if (request.method === 'POST') {
      posts.push({ path, body: await request.json() })
      return send(cropReply)
    }
    if (path.startsWith('/api/job/'))
      return send(jobReplies.length > 1 ? jobReplies.shift()! : jobReplies[0]!)
    const id = path.split('/').pop() ?? ''
    return send({ status: 200, body: pointClouds[id] ?? pointClouds.pc_1 })
  }
  return { handler, posts }
}

function job(state: string, extra: Record<string, unknown> = {}) {
  return { id: 'job_9', type: 'crop', state, progress: null, resultId: null, error: null, ...extra }
}

async function mountPage(fetchImpl: (input: RequestInfo | URL) => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(fetchImpl as typeof fetch))
  let onPick: (point: Vec3) => void = () => {}
  const handle = {
    setPointSize: vi.fn<(size: number) => void>(),
    setColorMode: vi.fn<(mode: string) => void>(),
    resetView: vi.fn<() => void>(),
    dispose: vi.fn<() => void>(),
    enableMeasure: vi.fn<(callback: (point: Vec3) => void) => () => void>((callback) => {
      onPick = callback
      return () => {}
    }),
    project: vi.fn<(point: Vec3) => { x: number; y: number; visible: boolean }>(() => ({
      x: 0,
      y: 0,
      visible: true,
    })),
    onUpdate: vi.fn<(listener: () => void) => () => void>(() => () => {}),
  }
  vi.mocked(mountPotreeViewer).mockResolvedValue(handle as unknown as PotreeViewerHandle)
  const wrapper = mount(ViewerPage, {
    props: { id: 'pc_1' },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })
  await flushPromises()
  return { wrapper, pick: (point: Vec3) => onPick(point) }
}

type Page = Awaited<ReturnType<typeof mountPage>>

function button(page: Page, label: string) {
  const found = page.wrapper.findAll('button').find((b) => b.text() === label)
  if (!found) throw new Error(`no "${label}" button`)
  return found
}

async function selectRegion(page: Page) {
  await button(page, 'Pick region').trigger('click')
  await flushPromises()
  page.pick({ x: 500010, y: 2000020, z: 101 })
  page.pick({ x: 500040, y: 2000060, z: 104 })
  await flushPromises()
}

function status(page: Page) {
  return page.wrapper.get('.crop-request [role="status"]').text()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(checkWebGL).mockReturnValue(true)
  vi.mocked(mountPotreeViewer).mockReset()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('sending a crop from the viewer', () => {
  it('cannot send before a region is selected', async () => {
    const page = await mountPage(server({ status: 202, body: job('queued') }).handler)

    expect(button(page, 'Crop point cloud').attributes('disabled')).toBeDefined()
    expect(page.wrapper.text()).toContain('Select a valid region to crop.')
  })

  it('sends the picked region in world coordinates and opens the result', async () => {
    const api = server({ status: 202, body: job('queued') }, [
      { status: 200, body: job('running', { progress: 60 }) },
      { status: 200, body: job('succeeded', { progress: 100, resultId: 'pc_crop' }) },
    ])
    const page = await mountPage(api.handler)
    await selectRegion(page)

    await button(page, 'Crop point cloud').trigger('click')
    await vi.advanceTimersByTimeAsync(0)
    expect(status(page)).toContain('Crop queued')

    await vi.advanceTimersByTimeAsync(1000)
    expect(status(page)).toContain('Cropping… 60%')

    await vi.advanceTimersByTimeAsync(1000)
    expect(status(page)).toContain('Crop complete')
    expect(page.wrapper.get('.crop-request a').attributes('href')).toBe('/viewer/pc_crop')

    expect(api.posts).toEqual([
      {
        path: '/api/pointcloud/pc_1/crop',
        body: {
          bounds: {
            minX: 500010,
            minY: 2000020,
            minZ: 100,
            maxX: 500040,
            maxY: 2000060,
            maxZ: 110,
          },
          outputFormat: 'laz',
        },
      },
    ])
  })

  it('sends a typed region, cut to the point cloud, as LAS', async () => {
    const api = server({ status: 202, body: job('succeeded', { resultId: 'pc_crop' }) })
    const page = await mountPage(api.handler)
    const fields = page.wrapper.findAll('.crop-fields input')
    const values = [500050, 500200, 2000010, 2000020, 90, 105]
    for (const [index, value] of values.entries()) {
      await fields[index]!.setValue(String(value))
      await fields[index]!.trigger('change')
    }
    await page.wrapper.get('.crop-request select').setValue('las')

    await button(page, 'Crop point cloud').trigger('click')
    await flushPromises()

    expect(api.posts[0]?.body).toEqual({
      bounds: { minX: 500050, minY: 2000010, minZ: 100, maxX: 500100, maxY: 2000020, maxZ: 105 },
      outputFormat: 'las',
    })
  })

  it('does not send a region outside the point cloud', async () => {
    const api = server({ status: 202, body: job('queued') })
    const page = await mountPage(api.handler)
    const fields = page.wrapper.findAll('.crop-fields input')
    const values = [600000, 600010, 3000000, 3000010, 0, 5]
    for (const [index, value] of values.entries()) {
      await fields[index]!.setValue(String(value))
      await fields[index]!.trigger('change')
    }

    expect(page.wrapper.text()).toContain('does not overlap the point cloud')
    expect(button(page, 'Crop point cloud').attributes('disabled')).toBeDefined()
    expect(api.posts).toEqual([])
  })

  it('shows why the server refused the crop, without its text', async () => {
    const api = server({
      status: 409,
      body: {
        error: { code: 'CONFLICT', message: '/srv/data/x', requestId: 'req_1', details: {} },
      },
    })
    const page = await mountPage(api.handler)
    await selectRegion(page)

    await button(page, 'Crop point cloud').trigger('click')
    await flushPromises()

    const alert = page.wrapper.get('.crop-request [role="alert"]').text()
    expect(alert).toContain('not ready to crop yet')
    expect(page.wrapper.text()).not.toContain('/srv/data')
  })
})

describe('opening the crop result', () => {
  it('shows the result without the region or measurement of the original', async () => {
    const api = server({ status: 202, body: job('queued') }, [
      { status: 200, body: job('succeeded', { progress: 100, resultId: 'pc_crop' }) },
    ])
    const page = await mountPage(api.handler)
    await button(page, 'Measure').trigger('click')
    await flushPromises()
    page.pick({ x: 500020, y: 2000030, z: 102 })
    page.pick({ x: 500030, y: 2000040, z: 103 })
    await flushPromises()
    expect(page.wrapper.find('.measure-panel .measure-results').exists()).toBe(true)
    await selectRegion(page)
    await button(page, 'Crop point cloud').trigger('click')
    await vi.advanceTimersByTimeAsync(1000)
    expect(page.wrapper.get('.crop-request a').attributes('href')).toBe('/viewer/pc_crop')

    // The link reuses this page with the result's id.
    await page.wrapper.setProps({ id: 'pc_crop' })
    await flushPromises()

    expect(vi.mocked(mountPotreeViewer)).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.stringContaining('/api/pointcloud/pc_crop/viewer/metadata.json'),
    )
    expect(page.wrapper.text()).toContain('survey-crop.laz')
    expect(page.wrapper.find('.measure-panel .measure-results').exists()).toBe(false)
    expect(button(page, 'Measure').attributes('aria-pressed')).toBe('false')
    for (const field of page.wrapper.findAll('.crop-fields input')) {
      expect((field.element as HTMLInputElement).value).toBe('')
    }
    expect(button(page, 'Pick region').exists()).toBe(true)
    expect(button(page, 'Crop point cloud').attributes('disabled')).toBeDefined()
    expect(status(page)).not.toContain('Crop complete')
  })

  it('links the result back to the point cloud it was cropped from', async () => {
    const page = await mountPage(server({ status: 202, body: job('queued') }).handler)

    await page.wrapper.setProps({ id: 'pc_crop' })
    await flushPromises()

    const metadata = page.wrapper.get('.metadata-panel')
    expect(metadata.text()).toContain('Cropped from')
    expect(metadata.get('a').attributes('href')).toBe('/viewer/pc_1')
  })
})
