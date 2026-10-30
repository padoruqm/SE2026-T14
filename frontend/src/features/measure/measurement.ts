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

/**
 * Convert a point in a local frame, whose origin sits at `offset` in world
 * coordinates, to world coordinates. Large survey coordinates are stored as small
 * local values plus an offset so they keep precision in 32-bit GPU buffers.
 */
export function offsetToWorld(local: Vec3, offset: Vec3): Vec3 {
  assertFinitePoint(local, 'local')
  assertFinitePoint(offset, 'offset')
  return { x: local.x + offset.x, y: local.y + offset.y, z: local.z + offset.z }
}

export function worldToOffset(world: Vec3, offset: Vec3): Vec3 {
  assertFinitePoint(world, 'world')
  assertFinitePoint(offset, 'offset')
  return { x: world.x - offset.x, y: world.y - offset.y, z: world.z - offset.z }
}
