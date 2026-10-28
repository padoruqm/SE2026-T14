export interface Vec3 {
  x: number
  y: number
  z: number
}

export interface DistanceMeasurement {
  from: Vec3
  to: Vec3
  /** Straight-line distance, in dataset units. */
  distance: number
  /** Distance in the XY plane, in dataset units. */
  horizontal: number
  /** `to.z - from.z`; positive when the second point is higher. */
  vertical: number
}

function assertFinitePoint(point: Vec3, name: string): void {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || !Number.isFinite(point.z)) {
    throw new RangeError(`${name} must have finite x, y and z`)
  }
}

export function distance(a: Vec3, b: Vec3): number {
  assertFinitePoint(a, 'a')
  assertFinitePoint(b, 'b')
  return Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z)
}

export function measureDistance(from: Vec3, to: Vec3): DistanceMeasurement {
  assertFinitePoint(from, 'from')
  assertFinitePoint(to, 'to')
  const dx = to.x - from.x
  const dy = to.y - from.y
  const dz = to.z - from.z
  return {
    from: { ...from },
    to: { ...to },
    distance: Math.hypot(dx, dy, dz),
    horizontal: Math.hypot(dx, dy),
    vertical: dz,
  }
}
