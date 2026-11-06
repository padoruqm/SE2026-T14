import { computed, ref } from 'vue'

import { measureDistance, type DistanceMeasurement, type Vec3 } from './measurement'

const MAX_POINTS = 2

/**
 * State of the Measure tool: up to two picked points. One point shows its
 * coordinates, two show the distance between them. A third pick starts over.
 * Nothing here touches the point cloud, so measuring never changes the data.
 */
export function useMeasure() {
  const active = ref(false)
  const points = ref<Vec3[]>([])
  const confirmingClear = ref(false)

  const coordinates = computed<Vec3 | null>(() =>
    points.value.length === 1 ? (points.value[0] ?? null) : null,
  )
  const measurement = computed<DistanceMeasurement | null>(() => {
    const [from, to] = points.value
    return points.value.length === MAX_POINTS && from && to ? measureDistance(from, to) : null
  })

  function start(): void {
    active.value = true
  }

  function stop(): void {
    active.value = false
    confirmingClear.value = false
  }

  function addPoint(point: Vec3): void {
    if (!active.value || confirmingClear.value) return
    if (![point.x, point.y, point.z].every(Number.isFinite)) return

    const copy = { x: point.x, y: point.y, z: point.z }
    points.value = points.value.length >= MAX_POINTS ? [copy] : [...points.value, copy]
  }

  function requestClear(): void {
    if (points.value.length > 0) confirmingClear.value = true
  }

  function confirmClear(): void {
    if (!confirmingClear.value) return
    points.value = []
    confirmingClear.value = false
  }

  function cancelClear(): void {
    confirmingClear.value = false
  }

  return {
    active,
    points,
    coordinates,
    measurement,
    confirmingClear,
    start,
    stop,
    addPoint,
    requestClear,
    confirmClear,
    cancelClear,
  }
}
