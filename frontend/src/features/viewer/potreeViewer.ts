// Potree 1.8.2 is a classic script that sets `window.Potree` and finds its workers
// through `document.currentScript`, so it is served from public/potree (see
// scripts/fetch-potree.sh) and loaded with script tags instead of being bundled.

import type { Vec3 } from '@/features/measure'

import { projectToScreen, type CameraLike, type ScreenPoint } from './projection'

interface PotreeRenderer {
  domElement: HTMLElement
  setAnimationLoop(callback: null): void
  dispose(): void
  forceContextLoss(): void
}

interface PotreeMaterial {
  size: number
  activeAttributeName: string
}

interface PotreePointCloud {
  material: PotreeMaterial
}

interface PotreeViewer {
  renderer: PotreeRenderer
  scene: {
    addPointCloud(pointCloud: unknown): void
    pointclouds: unknown[]
    getActiveCamera(): CameraLike
  }
  addEventListener(type: 'update', listener: () => void): void
  removeEventListener(type: 'update', listener: () => void): void
  setPointBudget(budget: number): void
  setEDLEnabled(enabled: boolean): void
  fitToScreen(): void
}

interface PotreeUtils {
  /** `mouse` is in pixels from the top left of the canvas; `location` is in world coordinates. */
  getMousePointCloudIntersection(
    mouse: { x: number; y: number },
    camera: CameraLike,
    viewer: PotreeViewer,
    pointClouds: unknown[],
  ): { location: Vec3 } | null
}

export interface PotreeGlobal {
  Viewer: new (element: HTMLElement) => PotreeViewer
  Utils: PotreeUtils
  loadPointCloud(url: string, name?: string): Promise<{ pointcloud: unknown }>
}

declare global {
  interface Window {
    Potree?: PotreeGlobal
  }
}

export type ColorMode = 'rgb' | 'elevation' | 'intensity'

// Potree names the attribute that colors the points; RGB is called `rgba`.
const COLOR_ATTRIBUTES: Record<ColorMode, string> = {
  rgb: 'rgba',
  elevation: 'elevation',
  intensity: 'intensity',
}

export interface PotreeViewerHandle {
  setPointSize(size: number): void
  setColorMode(mode: ColorMode): void
  resetView(): void
  /**
   * Call `onPick` with the world coordinates of the point under the cursor after a
   * click. Drags (camera moves) are ignored. Returns a function that stops picking.
   */
  enableMeasure(onPick: (point: Vec3) => void): () => void
  /** Canvas pixel position of a world point, for drawing markers over the viewer. */
  project(point: Vec3): ScreenPoint
  /** Call `listener` after every frame the viewer updates. Returns an unsubscribe function. */
  onUpdate(listener: () => void): () => void
  dispose(): void
}

/** A pointer that moves farther than this between press and release is a drag, not a click. */
const MAX_CLICK_MOVEMENT_PX = 4

const SCRIPTS = [
  'libs/jquery-3.1.1.min.js',
  'libs/BinaryHeap.js',
  'libs/tween.min.js',
  'libs/proj4.js',
  'potree.js',
]

let loading: Promise<PotreeGlobal> | null = null

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = false
    script.onload = () => resolve()
    script.onerror = () => reject(new Error(`Failed to load ${src}`))
    document.head.append(script)
  })
}

export function loadPotree(baseUrl = `${import.meta.env.BASE_URL}potree/`): Promise<PotreeGlobal> {
  loading ??= Promise.all(SCRIPTS.map((path) => loadScript(baseUrl + path))).then(() => {
    if (typeof window.Potree?.Viewer !== 'function') throw new Error('Potree failed to load')
    return window.Potree
  })
  loading.catch(() => {
    loading = null
  })
  return loading
}

export async function mountPotreeViewer(
  element: HTMLElement,
  pointCloudUrl: string,
  potree?: PotreeGlobal,
): Promise<PotreeViewerHandle> {
  const Potree = potree ?? (await loadPotree())
  const viewer = new Potree.Viewer(element)
  viewer.setEDLEnabled(false)
  viewer.setPointBudget(1_000_000)

  let disposed = false
  const cleanups = new Set<() => void>()
  let loaded: PotreePointCloud | null = null
  // Remembered so a change made while the cloud is still loading is applied once it arrives.
  let pointSize: number | null = null
  let colorMode: ColorMode | null = null

  // Only material settings change, so the point cloud is never converted or fetched again.
  function applyMaterial() {
    if (!loaded) return
    if (pointSize !== null) loaded.material.size = pointSize
    if (colorMode !== null) loaded.material.activeAttributeName = COLOR_ATTRIBUTES[colorMode]
  }

  Potree.loadPointCloud(pointCloudUrl).then(({ pointcloud }) => {
    if (disposed) return
    loaded = pointcloud as PotreePointCloud
    applyMaterial()
    viewer.scene.addPointCloud(pointcloud)
    viewer.fitToScreen()
  })

  return {
    setPointSize(size) {
      pointSize = size
      applyMaterial()
    },
    setColorMode(mode) {
      colorMode = mode
      applyMaterial()
    },
    resetView() {
      viewer.fitToScreen()
    },
    enableMeasure(onPick) {
      const canvas = viewer.renderer.domElement
      const previousCursor = canvas.style.cursor
      let pressedAt: { x: number; y: number } | null = null

      const onDown = (event: PointerEvent) => {
        pressedAt = event.button === 0 ? { x: event.clientX, y: event.clientY } : null
      }
      const onUp = (event: PointerEvent) => {
        const start = pressedAt
        pressedAt = null
        if (!start || event.button !== 0) return
        if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > MAX_CLICK_MOVEMENT_PX) {
          return
        }
        const bounds = canvas.getBoundingClientRect()
        const hit = Potree.Utils.getMousePointCloudIntersection(
          { x: event.clientX - bounds.left, y: event.clientY - bounds.top },
          viewer.scene.getActiveCamera(),
          viewer,
          viewer.scene.pointclouds,
        )
        if (hit) onPick({ x: hit.location.x, y: hit.location.y, z: hit.location.z })
      }

      canvas.addEventListener('pointerdown', onDown)
      canvas.addEventListener('pointerup', onUp)
      canvas.style.cursor = 'crosshair'

      const disable = () => {
        if (!cleanups.delete(disable)) return
        canvas.removeEventListener('pointerdown', onDown)
        canvas.removeEventListener('pointerup', onUp)
        canvas.style.cursor = previousCursor
      }
      cleanups.add(disable)
      return disable
    },
    project(point) {
      const canvas = viewer.renderer.domElement
      return projectToScreen(
        point,
        viewer.scene.getActiveCamera(),
        canvas.clientWidth,
        canvas.clientHeight,
      )
    },
    onUpdate(listener) {
      viewer.addEventListener('update', listener)
      const unsubscribe = () => {
        if (!cleanups.delete(unsubscribe)) return
        viewer.removeEventListener('update', listener)
      }
      cleanups.add(unsubscribe)
      return unsubscribe
    },
    dispose() {
      if (disposed) return
      disposed = true
      for (const cleanup of cleanups) cleanup()
      // Potree has no dispose of its own: stop its render loop, release the WebGL
      // context and remove the canvas and overlays it added to the element.
      viewer.renderer.setAnimationLoop(null)
      viewer.renderer.dispose()
      viewer.renderer.forceContextLoss()
      element.replaceChildren()
    },
  }
}
