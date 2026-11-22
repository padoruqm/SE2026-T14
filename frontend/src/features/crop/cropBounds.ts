import type { Vec3 } from '@/features/measure'

/** World-coordinate box; the same shape as `Bounds` in `openapi.yaml`, so it can be sent as is. */
export interface CropBounds {
  minX: number
  minY: number
  minZ: number
  maxX: number
  maxY: number
  maxZ: number
}

export type CropError = 'INVALID' | 'EMPTY' | 'OUTSIDE_DATASET'

export type CropResult = { ok: true; bounds: CropBounds } | { ok: false; error: CropError }

export const CROP_ERROR_MESSAGES: Record<CropError, string> = {
  INVALID: 'Every value must be a finite number.',
  EMPTY: 'The region has no area. Make it wider and deeper than zero.',
  OUTSIDE_DATASET: 'The region does not overlap the point cloud.',
}

const KEYS = ['minX', 'minY', 'minZ', 'maxX', 'maxY', 'maxZ'] as const

export function isFiniteBounds(bounds: CropBounds): boolean {
  return KEYS.every((key) => Number.isFinite(bounds[key]))
}

/** Swap min and max on any axis that was dragged backwards. */
export function normalizeBounds(bounds: CropBounds): CropBounds {
  if (!isFiniteBounds(bounds)) throw new RangeError('bounds must be finite numbers')
  return {
    minX: Math.min(bounds.minX, bounds.maxX),
    minY: Math.min(bounds.minY, bounds.maxY),
    minZ: Math.min(bounds.minZ, bounds.maxZ),
    maxX: Math.max(bounds.minX, bounds.maxX),
    maxY: Math.max(bounds.minY, bounds.maxY),
    maxZ: Math.max(bounds.minZ, bounds.maxZ),
  }
}

/**
 * A region is empty when it has no area in X or Y. A zero height is allowed:
 * a flat dataset has the same minimum and maximum Z.
 */
export function isEmpty(bounds: CropBounds): boolean {
  const { minX, minY, maxX, maxY } = normalizeBounds(bounds)
  return maxX <= minX || maxY <= minY
}

/**
 * Cut a region down to the dataset. Returns null when they do not overlap in
 * X and Y (touching along an edge is not an overlap). Z only needs to be inside
 * the dataset's range, not to overlap it by volume.
 */
export function clampToDatasetBounds(bounds: CropBounds, dataset: CropBounds): CropBounds | null {
  const region = normalizeBounds(bounds)
  const limit = normalizeBounds(dataset)
  const clamped: CropBounds = {
    minX: Math.max(region.minX, limit.minX),
    minY: Math.max(region.minY, limit.minY),
    minZ: Math.max(region.minZ, limit.minZ),
    maxX: Math.min(region.maxX, limit.maxX),
    maxY: Math.min(region.maxY, limit.maxY),
    maxZ: Math.min(region.maxZ, limit.maxZ),
  }
  if (clamped.maxX <= clamped.minX || clamped.maxY <= clamped.minY) return null
  if (clamped.maxZ < clamped.minZ) return null
  return clamped
}

/**
 * Turn what the user selected into the box to send: reversed axes are swapped,
 * an empty or non-numeric region is an error, and with known dataset bounds the
 * box is cut to them. A region fully outside the dataset is an error.
 */
export function resolveCropBounds(raw: CropBounds, dataset: CropBounds | null): CropResult {
  if (!isFiniteBounds(raw)) return { ok: false, error: 'INVALID' }
  const normalized = normalizeBounds(raw)
  if (isEmpty(normalized)) return { ok: false, error: 'EMPTY' }
  if (dataset === null || !isFiniteBounds(dataset)) return { ok: true, bounds: normalized }

  const clamped = clampToDatasetBounds(normalized, dataset)
  return clamped ? { ok: true, bounds: clamped } : { ok: false, error: 'OUTSIDE_DATASET' }
}

/**
 * The box spanned by two picked corners. Picking lands on the surface, so the
 * height of the box comes from `zRange` (the dataset's) when it is known.
 */
export function boundsFromCorners(
  a: Vec3,
  b: Vec3,
  zRange: { minZ: number; maxZ: number } | null,
): CropBounds {
  return normalizeBounds({
    minX: a.x,
    minY: a.y,
    minZ: zRange?.minZ ?? a.z,
    maxX: b.x,
    maxY: b.y,
    maxZ: zRange?.maxZ ?? b.z,
  })
}

/** The 8 corners of a box, for drawing it. */
export function boxCorners(bounds: CropBounds): Vec3[] {
  const { minX, minY, minZ, maxX, maxY, maxZ } = bounds
  return [
    { x: minX, y: minY, z: minZ },
    { x: maxX, y: minY, z: minZ },
    { x: maxX, y: maxY, z: minZ },
    { x: minX, y: maxY, z: minZ },
    { x: minX, y: minY, z: maxZ },
    { x: maxX, y: minY, z: maxZ },
    { x: maxX, y: maxY, z: maxZ },
    { x: minX, y: maxY, z: maxZ },
  ]
}

/** Index pairs of `boxCorners` joined by an edge. */
export const BOX_EDGES: readonly (readonly [number, number])[] = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 0],
  [4, 5],
  [5, 6],
  [6, 7],
  [7, 4],
  [0, 4],
  [1, 5],
  [2, 6],
  [3, 7],
]
