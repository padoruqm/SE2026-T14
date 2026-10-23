// Potree 1.8.2 is a classic script that sets `window.Potree` and finds its workers
// through `document.currentScript`, so it is served from public/potree (see
// scripts/fetch-potree.sh) and loaded with script tags instead of being bundled.

interface PotreeRenderer {
  setAnimationLoop(callback: null): void
  dispose(): void
  forceContextLoss(): void
}

interface PotreeViewer {
  renderer: PotreeRenderer
  scene: { addPointCloud(pointCloud: unknown): void }
  setPointBudget(budget: number): void
  setEDLEnabled(enabled: boolean): void
  fitToScreen(): void
}

export interface PotreeGlobal {
  Viewer: new (element: HTMLElement) => PotreeViewer
  loadPointCloud(url: string, name?: string): Promise<{ pointcloud: unknown }>
}

declare global {
  interface Window {
    Potree?: PotreeGlobal
  }
}

export interface PotreeViewerHandle {
  dispose(): void
}

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
  Potree.loadPointCloud(pointCloudUrl).then(({ pointcloud }) => {
    if (disposed) return
    viewer.scene.addPointCloud(pointcloud)
    viewer.fitToScreen()
  })

  return {
    dispose() {
      if (disposed) return
      disposed = true
      // Potree has no dispose of its own: stop its render loop, release the WebGL
      // context and remove the canvas and overlays it added to the element.
      viewer.renderer.setAnimationLoop(null)
      viewer.renderer.dispose()
      viewer.renderer.forceContextLoss()
      element.replaceChildren()
    },
  }
}
