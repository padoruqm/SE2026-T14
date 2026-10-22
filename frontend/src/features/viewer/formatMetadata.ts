import type { Bounds } from '@/api/generated'

const pointCountFormat = new Intl.NumberFormat('en-US')

export function formatPointCount(count: number): string {
  return pointCountFormat.format(count)
}

export function formatCoordinate(value: number): string {
  return value.toFixed(3)
}

export interface BoundsRow {
  axis: 'X' | 'Y' | 'Z'
  min: string
  max: string
  extent: string
}

export function boundsRows(bounds: Bounds): BoundsRow[] {
  const axes = [
    { axis: 'X', min: bounds.minX, max: bounds.maxX },
    { axis: 'Y', min: bounds.minY, max: bounds.maxY },
    { axis: 'Z', min: bounds.minZ, max: bounds.maxZ },
  ] as const

  return axes.map(({ axis, min, max }) => ({
    axis,
    min: formatCoordinate(min),
    max: formatCoordinate(max),
    extent: formatCoordinate(max - min),
  }))
}
