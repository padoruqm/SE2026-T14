import { describe, expect, it } from 'vitest'

import {
  boundsFromCorners,
  boxCorners,
  clampToDatasetBounds,
  isEmpty,
  normalizeBounds,
  resolveCropBounds,
  type CropBounds,
} from '../cropBounds'

const dataset: CropBounds = {
  minX: 500000,
  minY: 2000000,
  minZ: 100,
  maxX: 500100,
  maxY: 2000100,
  maxZ: 110,
}

function box(overrides: Partial<CropBounds> = {}): CropBounds {
  return { ...dataset, ...overrides }
}

describe('normalizeBounds', () => {
  it('swaps min and max on an axis that was dragged backwards', () => {
    const result = normalizeBounds({
      minX: 500050,
      minY: 2000010,
      minZ: 105,
      maxX: 500020,
      maxY: 2000080,
      maxZ: 101,
    })
    expect(result).toEqual({
      minX: 500020,
      minY: 2000010,
      minZ: 101,
      maxX: 500050,
      maxY: 2000080,
      maxZ: 105,
    })
  })

  it('keeps a box that is already in order', () => {
    expect(normalizeBounds(dataset)).toEqual(dataset)
  })

  it('rejects values that are not finite', () => {
    expect(() => normalizeBounds(box({ minX: NaN }))).toThrow(RangeError)
    expect(() => normalizeBounds(box({ maxZ: Infinity }))).toThrow(RangeError)
  })
})

describe('isEmpty', () => {
  it('is true with no width or no depth, in either order', () => {
    expect(isEmpty(box({ minX: 500010, maxX: 500010 }))).toBe(true)
    expect(isEmpty(box({ minY: 2000010, maxY: 2000010 }))).toBe(true)
  })

  it('allows a flat box with no height', () => {
    expect(isEmpty(box({ minZ: 100, maxZ: 100 }))).toBe(false)
  })

  it('is false for a region with area', () => {
    expect(isEmpty(dataset)).toBe(false)
  })
})

describe('clampToDatasetBounds', () => {
  it('cuts a region that sticks out of the dataset', () => {
    const region = box({ minX: 499900, maxX: 500050, minZ: 90, maxZ: 120 })
    expect(clampToDatasetBounds(region, dataset)).toEqual(box({ maxX: 500050 }))
  })

  it('returns a region inside the dataset unchanged', () => {
    const region = box({ minX: 500010, maxX: 500020, minY: 2000010, maxY: 2000020 })
    expect(clampToDatasetBounds(region, dataset)).toEqual(region)
  })

  it('returns null when the region is entirely outside', () => {
    expect(clampToDatasetBounds(box({ minX: 600000, maxX: 600100 }), dataset)).toBeNull()
  })

  it('returns null when the region only touches an edge', () => {
    expect(clampToDatasetBounds(box({ minX: 500100, maxX: 500200 }), dataset)).toBeNull()
  })

  it('returns null when the region is above or below the dataset', () => {
    expect(clampToDatasetBounds(box({ minZ: 200, maxZ: 300 }), dataset)).toBeNull()
  })

  it('works with a reversed region', () => {
    const reversed = box({ minX: 500050, maxX: 500020 })
    expect(clampToDatasetBounds(reversed, dataset)).toEqual(box({ minX: 500020, maxX: 500050 }))
  })
})

describe('resolveCropBounds', () => {
  it('returns the reordered and clamped box', () => {
    const result = resolveCropBounds({ ...dataset, minX: 500050, maxX: 499950 }, dataset)
    expect(result).toEqual({ ok: true, bounds: box({ minX: 500000, maxX: 500050 }) })
  })

  it('reports an empty region', () => {
    expect(resolveCropBounds(box({ minX: 500010, maxX: 500010 }), dataset)).toEqual({
      ok: false,
      error: 'EMPTY',
    })
  })

  it('reports a region outside the dataset', () => {
    expect(resolveCropBounds(box({ minX: 0, maxX: 10 }), dataset)).toEqual({
      ok: false,
      error: 'OUTSIDE_DATASET',
    })
  })

  it('reports values that are not numbers', () => {
    expect(resolveCropBounds(box({ minY: NaN }), dataset)).toEqual({ ok: false, error: 'INVALID' })
  })

  it('only reorders when the dataset bounds are unknown', () => {
    const region = box({ minX: 600000, maxX: 500000 })
    expect(resolveCropBounds(region, null)).toEqual({
      ok: true,
      bounds: box({ minX: 500000, maxX: 600000 }),
    })
  })
})

describe('boundsFromCorners', () => {
  const a = { x: 500080, y: 2000010, z: 104 }
  const b = { x: 500020, y: 2000090, z: 103 }

  it('orders the corners and takes the height from the dataset', () => {
    expect(boundsFromCorners(a, b, dataset)).toEqual({
      minX: 500020,
      minY: 2000010,
      minZ: 100,
      maxX: 500080,
      maxY: 2000090,
      maxZ: 110,
    })
  })

  it('falls back to the picked heights when the dataset is unknown', () => {
    const result = boundsFromCorners(a, b, null)
    expect(result.minZ).toBe(103)
    expect(result.maxZ).toBe(104)
  })
})

describe('boxCorners', () => {
  it('lists the 8 distinct corners of the box', () => {
    const corners = boxCorners(dataset)
    expect(corners).toHaveLength(8)
    expect(new Set(corners.map((c) => `${c.x},${c.y},${c.z}`)).size).toBe(8)
  })
})
