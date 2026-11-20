import { computed, ref, type MaybeRefOrGetter, toValue } from 'vue'

import type { Vec3 } from '@/features/measure'

import { boundsFromCorners, resolveCropBounds, type CropBounds, type CropError } from './cropBounds'

/**
 * State of the Crop tool: a region the user picked (two opposite corners in the
 * viewer) or typed in. `bounds` is the box that would be sent to the crop API, in
 * world coordinates; it is null while there is no valid region. Nothing here
 * changes the point cloud.
 */
export function useCropSelection(dataset: MaybeRefOrGetter<CropBounds | null>) {
  const picking = ref(false)
  const corners = ref<Vec3[]>([])
  const raw = ref<CropBounds | null>(null)

  const result = computed(() => (raw.value ? resolveCropBounds(raw.value, toValue(dataset)) : null))
  const bounds = computed<CropBounds | null>(() => (result.value?.ok ? result.value.bounds : null))
  const error = computed<CropError | null>(() =>
    result.value && !result.value.ok ? result.value.error : null,
  )
  /** The region as selected or typed, valid or not, so it can still be drawn and fixed. */
  const selection = computed<CropBounds | null>(() => raw.value)

  function startPicking(): void {
    picking.value = true
  }

  function stopPicking(): void {
    picking.value = false
  }

  function addCorner(point: Vec3): void {
    if (!picking.value) return
    if (![point.x, point.y, point.z].every(Number.isFinite)) return

    const copy = { x: point.x, y: point.y, z: point.z }
    // A third pick starts a new region.
    const next = corners.value.length >= 2 ? [copy] : [...corners.value, copy]
    corners.value = next
    const [first, second] = next
    if (first && second) {
      const data = toValue(dataset)
      raw.value = boundsFromCorners(first, second, data)
      picking.value = false
    } else {
      raw.value = null
    }
  }

  /** Replace the region with typed values; later edits keep what the user typed. */
  function setBounds(next: CropBounds): void {
    corners.value = []
    raw.value = { ...next }
  }

  function clear(): void {
    corners.value = []
    raw.value = null
  }

  return {
    picking,
    corners,
    selection,
    bounds,
    error,
    startPicking,
    stopPicking,
    addCorner,
    setBounds,
    clear,
  }
}
