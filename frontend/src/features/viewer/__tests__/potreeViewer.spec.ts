import { describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import { mountPotreeViewer, type PotreeGlobal } from '../potreeViewer'

function fakePotree() {
  const renderer = {
    setAnimationLoop: vi.fn<(callback: null) => void>(),
    dispose: vi.fn<() => void>(),
    forceContextLoss: vi.fn<() => void>(),
  }
  const viewer = {
    renderer,
    scene: { addPointCloud: vi.fn<(pointCloud: unknown) => void>() },
    setPointBudget: vi.fn<(budget: number) => void>(),
    setEDLEnabled: vi.fn<(enabled: boolean) => void>(),
    fitToScreen: vi.fn<() => void>(),
  }
  type Loaded = { pointcloud: unknown }
  let resolveLoad: (value: Loaded) => void = () => {}
  const potree = {
    Viewer: vi.fn<(element: HTMLElement) => typeof viewer>(function (element) {
      element.append(document.createElement('canvas'))
      return viewer
    }),
    loadPointCloud: vi.fn<(url: string) => Promise<Loaded>>(
      () => new Promise((resolve) => (resolveLoad = resolve)),
    ),
  }
  return {
    potree: potree as unknown as PotreeGlobal,
    viewer,
    loaded: (pointcloud: unknown) => resolveLoad({ pointcloud }),
  }
}

function cloud() {
  return { material: { size: 1, activeAttributeName: 'rgba' } }
}

describe('mountPotreeViewer', () => {
  it('creates a viewer in the element and adds the loaded point cloud', async () => {
    const { potree, viewer, loaded } = fakePotree()
    const element = document.createElement('div')

    await mountPotreeViewer(element, '/data/pc_1/metadata.json', potree)
    const pointcloud = cloud()
    loaded(pointcloud)
    await flushPromises()

    expect(potree.Viewer).toHaveBeenCalledWith(element)
    expect(potree.loadPointCloud).toHaveBeenCalledWith('/data/pc_1/metadata.json')
    expect(viewer.scene.addPointCloud).toHaveBeenCalledWith(pointcloud)
    expect(viewer.fitToScreen).toHaveBeenCalled()
  })

  it('stops rendering, releases the WebGL context and empties the element on dispose', async () => {
    const { potree, viewer } = fakePotree()
    const element = document.createElement('div')
    const handle = await mountPotreeViewer(element, '/cloud.json', potree)

    handle.dispose()
    handle.dispose()

    expect(viewer.renderer.setAnimationLoop).toHaveBeenCalledExactlyOnceWith(null)
    expect(viewer.renderer.dispose).toHaveBeenCalledOnce()
    expect(viewer.renderer.forceContextLoss).toHaveBeenCalledOnce()
    expect(element.children).toHaveLength(0)
  })

  it('ignores a point cloud that finishes loading after dispose', async () => {
    const { potree, viewer, loaded } = fakePotree()
    const handle = await mountPotreeViewer(document.createElement('div'), '/cloud.json', potree)

    handle.dispose()
    loaded(cloud())
    await flushPromises()

    expect(viewer.scene.addPointCloud).not.toHaveBeenCalled()
  })

  it('changes point size and color on the loaded cloud without loading it again', async () => {
    const { potree, loaded } = fakePotree()
    const handle = await mountPotreeViewer(document.createElement('div'), '/cloud.json', potree)
    const pointcloud = cloud()
    loaded(pointcloud)
    await flushPromises()

    handle.setPointSize(3)
    handle.setColorMode('elevation')

    expect(pointcloud.material.size).toBe(3)
    expect(pointcloud.material.activeAttributeName).toBe('elevation')
    expect(potree.loadPointCloud).toHaveBeenCalledOnce()
  })

  it('applies settings chosen before the cloud finished loading', async () => {
    const { potree, loaded } = fakePotree()
    const handle = await mountPotreeViewer(document.createElement('div'), '/cloud.json', potree)

    handle.setPointSize(2)
    handle.setColorMode('intensity')
    const pointcloud = cloud()
    loaded(pointcloud)
    await flushPromises()

    expect(pointcloud.material.size).toBe(2)
    expect(pointcloud.material.activeAttributeName).toBe('intensity')
  })

  it('fits the camera to the cloud again on resetView', async () => {
    const { potree, viewer } = fakePotree()
    const handle = await mountPotreeViewer(document.createElement('div'), '/cloud.json', potree)

    handle.resetView()

    expect(viewer.fitToScreen).toHaveBeenCalledOnce()
  })
})
