import type { Vec3 } from '@/features/measure'

/** A column-major 4x4 matrix, as stored by three.js. */
interface Matrix4Like {
  elements: ArrayLike<number>
}

export interface CameraLike {
  matrixWorldInverse: Matrix4Like
  projectionMatrix: Matrix4Like
}

export interface ScreenPoint {
  /** Pixels from the left edge of the canvas. */
  x: number
  /** Pixels from the top edge of the canvas. */
  y: number
  /** False when the point is behind the camera or outside the view. */
  visible: boolean
}

function transform(matrix: ArrayLike<number>, v: readonly [number, number, number, number]) {
  const row = (r: number) =>
    matrix[r]! * v[0] + matrix[4 + r]! * v[1] + matrix[8 + r]! * v[2] + matrix[12 + r]! * v[3]
  return [row(0), row(1), row(2), row(3)] as const
}

/**
 * Project a world point to canvas pixels. World coordinates can be large (a UTM
 * easting is about 5e5), so this stays in doubles and does not go through a
 * 32-bit buffer.
 */
export function projectToScreen(
  point: Vec3,
  camera: CameraLike,
  width: number,
  height: number,
): ScreenPoint {
  const view = transform(camera.matrixWorldInverse.elements, [point.x, point.y, point.z, 1])
  const [cx, cy, cz, cw] = transform(camera.projectionMatrix.elements, view)

  if (!(cw > 0)) return { x: NaN, y: NaN, visible: false }

  const ndcX = cx / cw
  const ndcY = cy / cw
  const ndcZ = cz / cw
  return {
    x: ((ndcX + 1) / 2) * width,
    y: ((1 - ndcY) / 2) * height,
    visible: Math.abs(ndcX) <= 1 && Math.abs(ndcY) <= 1 && Math.abs(ndcZ) <= 1,
  }
}
