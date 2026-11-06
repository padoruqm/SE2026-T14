import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import { mountPotreeViewer, type PotreeGlobal } from '../potreeViewer'

type Listener = () => void
type Hit = { location: { x: number; y: number; z: number } } | null

function fakePotree(hit: Hit = { location: { x: 500001.25, y: 2000002.5, z: 100.75 } }) {
  const canvas = document.createElement('canvas')
  Object.defineProperty(canvas, 'clientWidth', { value: 800 })
  Object.defineProperty(canvas, 'clientHeight', { value: 600 })
  canvas.getBoundingClientRect = () => ({ left: 10, top: 20 }) as DOMRect

  const camera = {
    matrixWorldInverse: { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
    projectionMatrix: { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, -1, 0, 0, -0.2, 0] },
  }
  const updateListeners = new Set<Listener>()
  const viewer = {
    renderer: {
      domElement: canvas,
      setAnimationLoop: vi.fn<(callback: null) => void>(),
      dispose: vi.fn<() => void>(),
      forceContextLoss: vi.fn<() => void>(),
    },
    scene: {
      addPointCloud: vi.fn<(pointCloud: unknown) => void>(),
      pointclouds: ['cloud'],
      getActiveCamera: () => camera,
    },
    addEventListener: vi.fn<(type: string, listener: Listener) => void>((_type, listener) => {
      updateListeners.add(listener)
    }),
    removeEventListener: vi.fn<(type: string, listener: Listener) => void>((_type, listener) => {
      updateListeners.delete(listener)
    }),
    setPointBudget: vi.fn<(budget: number) => void>(),
    setEDLEnabled: vi.fn<(enabled: boolean) => void>(),
    fitToScreen: vi.fn<() => void>(),
  }
  const pick = vi.fn<
    (
      mouse: { x: number; y: number },
      camera: unknown,
      viewer: unknown,
      pointClouds: unknown[],
    ) => Hit
  >(() => hit)
  const potree = {
    Viewer: vi.fn<(element: HTMLElement) => typeof viewer>(function (element) {
      element.append(canvas)
      return viewer
    }),
    Utils: { getMousePointCloudIntersection: pick },
    loadPointCloud: vi.fn<(url: string) => Promise<{ pointcloud: unknown }>>(
      () => new Promise(() => {}),
    ),
  }
  return {
    potree: potree as unknown as PotreeGlobal,
    viewer,
    canvas,
    pick,
    fire: () => updateListeners.forEach((listener) => listener()),
    listenerCount: () => updateListeners.size,
  }
}

function pointer(canvas: HTMLElement, type: string, x: number, y: number, button = 0) {
  canvas.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, button, bubbles: true }))
}

function click(canvas: HTMLElement, x: number, y: number) {
  pointer(canvas, 'pointerdown', x, y)
  pointer(canvas, 'pointerup', x, y)
}

async function mount(hit?: Hit) {
  const fake = fakePotree(hit)
  const handle = await mountPotreeViewer(document.createElement('div'), '/cloud.json', fake.potree)
  await flushPromises()
  return { ...fake, handle }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('enableMeasure', () => {
  it('reports the world coordinates of a clicked point', async () => {
    const { handle, canvas, pick } = await mount()
    const onPick = vi.fn<(point: unknown) => void>()

    handle.enableMeasure(onPick)
    click(canvas, 110, 220)

    expect(onPick).toHaveBeenCalledExactlyOnceWith({ x: 500001.25, y: 2000002.5, z: 100.75 })
    expect(pick).toHaveBeenCalledOnce()
  })

  it('asks Potree to pick using canvas-relative pixels, its camera and its point clouds', async () => {
    const { handle, canvas, pick, viewer } = await mount()

    handle.enableMeasure(() => {})
    click(canvas, 110, 220)

    const [mouse, camera, passedViewer, pointClouds] = pick.mock.calls[0]!
    expect(mouse).toEqual({ x: 100, y: 200 })
    expect(camera).toBe(viewer.scene.getActiveCamera())
    expect(passedViewer).toBe(viewer)
    expect(pointClouds).toBe(viewer.scene.pointclouds)
  })

  it('returns plain coordinates, not the object Potree gave back', async () => {
    const location = { x: 1, y: 2, z: 3, extra: 'three.js internals' }
    const { handle, canvas } = await mount({ location })
    const onPick = vi.fn<(point: unknown) => void>()

    handle.enableMeasure(onPick)
    click(canvas, 5, 5)

    expect(onPick).toHaveBeenCalledWith({ x: 1, y: 2, z: 3 })
  })

  it('ignores a drag, which moves the camera', async () => {
    const { handle, canvas, pick } = await mount()
    const onPick = vi.fn<(point: unknown) => void>()

    handle.enableMeasure(onPick)
    pointer(canvas, 'pointerdown', 100, 100)
    pointer(canvas, 'pointerup', 130, 100)

    expect(onPick).not.toHaveBeenCalled()
    expect(pick).not.toHaveBeenCalled()
  })

  it('still treats a tiny movement as a click', async () => {
    const { handle, canvas } = await mount()
    const onPick = vi.fn<(point: unknown) => void>()

    handle.enableMeasure(onPick)
    pointer(canvas, 'pointerdown', 100, 100)
    pointer(canvas, 'pointerup', 102, 101)

    expect(onPick).toHaveBeenCalledOnce()
  })

  it('ignores the right and middle buttons, which pan and zoom', async () => {
    const { handle, canvas, pick } = await mount()
    handle.enableMeasure(() => {})

    for (const button of [1, 2]) {
      pointer(canvas, 'pointerdown', 50, 50, button)
      pointer(canvas, 'pointerup', 50, 50, button)
    }

    expect(pick).not.toHaveBeenCalled()
  })

  it('does nothing when the click hits no point', async () => {
    const { handle, canvas } = await mount(null)
    const onPick = vi.fn<(point: unknown) => void>()

    handle.enableMeasure(onPick)
    click(canvas, 50, 50)

    expect(onPick).not.toHaveBeenCalled()
  })

  it('needs a press on the canvas before a release counts', async () => {
    const { handle, canvas, pick } = await mount()
    handle.enableMeasure(() => {})

    pointer(canvas, 'pointerup', 50, 50)

    expect(pick).not.toHaveBeenCalled()
  })

  it('shows a crosshair while measuring and restores the cursor after', async () => {
    const { handle, canvas } = await mount()
    canvas.style.cursor = 'grab'

    const disable = handle.enableMeasure(() => {})
    expect(canvas.style.cursor).toBe('crosshair')

    disable()
    expect(canvas.style.cursor).toBe('grab')
  })

  it('stops picking once disabled, and disabling twice is harmless', async () => {
    const { handle, canvas, pick } = await mount()

    const disable = handle.enableMeasure(() => {})
    disable()
    disable()
    click(canvas, 50, 50)

    expect(pick).not.toHaveBeenCalled()
  })

  it('stops picking when the viewer is disposed', async () => {
    const { handle, canvas, pick } = await mount()
    handle.enableMeasure(() => {})

    handle.dispose()
    click(canvas, 50, 50)

    expect(pick).not.toHaveBeenCalled()
  })
})

describe('project', () => {
  it('maps a world point through the active camera to canvas pixels', async () => {
    const { handle } = await mount()

    const result = handle.project({ x: 0, y: 0, z: -10 })

    expect(result.visible).toBe(true)
    expect(result.x).toBeCloseTo(400, 6)
    expect(result.y).toBeCloseTo(300, 6)
  })
})

describe('onUpdate', () => {
  it('calls the listener on every update until unsubscribed', async () => {
    const { handle, fire } = await mount()
    const listener = vi.fn<() => void>()

    const unsubscribe = handle.onUpdate(listener)
    fire()
    fire()
    unsubscribe()
    fire()

    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('removes its listeners when the viewer is disposed', async () => {
    const { handle, listenerCount } = await mount()
    handle.onUpdate(() => {})
    expect(listenerCount()).toBe(1)

    handle.dispose()

    expect(listenerCount()).toBe(0)
  })
})
