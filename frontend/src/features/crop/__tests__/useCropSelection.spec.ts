import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import type { CropBounds } from '../cropBounds'
import { useCropSelection } from '../useCropSelection'

const dataset: CropBounds = {
  minX: 500000,
  minY: 2000000,
  minZ: 100,
  maxX: 500100,
  maxY: 2000100,
  maxZ: 110,
}

describe('useCropSelection', () => {
  it('ignores picks while picking is off', () => {
    const crop = useCropSelection(dataset)
    crop.addCorner({ x: 500010, y: 2000010, z: 101 })
    expect(crop.corners.value).toEqual([])
    expect(crop.bounds.value).toBeNull()
  })

  it('makes a box from two picked corners and stops picking', () => {
    const crop = useCropSelection(dataset)
    crop.startPicking()
    crop.addCorner({ x: 500080, y: 2000010, z: 104 })
    expect(crop.bounds.value).toBeNull()
    expect(crop.picking.value).toBe(true)

    crop.addCorner({ x: 500020, y: 2000090, z: 103 })
    expect(crop.bounds.value).toEqual({
      minX: 500020,
      minY: 2000010,
      minZ: 100,
      maxX: 500080,
      maxY: 2000090,
      maxZ: 110,
    })
    expect(crop.picking.value).toBe(false)
  })

  it('reports an error for two corners with the same position', () => {
    const crop = useCropSelection(dataset)
    crop.startPicking()
    crop.addCorner({ x: 500010, y: 2000010, z: 101 })
    crop.addCorner({ x: 500010, y: 2000010, z: 101 })
    expect(crop.bounds.value).toBeNull()
    expect(crop.error.value).toBe('EMPTY')
  })

  it('ignores a pick that is not finite', () => {
    const crop = useCropSelection(dataset)
    crop.startPicking()
    crop.addCorner({ x: NaN, y: 0, z: 0 })
    expect(crop.corners.value).toEqual([])
  })

  it('accepts typed values, reordered and cut to the dataset', () => {
    const crop = useCropSelection(dataset)
    crop.setBounds({ ...dataset, minX: 500050, maxX: 499900 })
    expect(crop.bounds.value).toEqual({ ...dataset, minX: 500000, maxX: 500050 })
    expect(crop.selection.value).toEqual({ ...dataset, minX: 500050, maxX: 499900 })
  })

  it('reports a typed region outside the dataset and keeps what was typed', () => {
    const crop = useCropSelection(dataset)
    const outside = { ...dataset, minX: 0, maxX: 10 }
    crop.setBounds(outside)
    expect(crop.bounds.value).toBeNull()
    expect(crop.error.value).toBe('OUTSIDE_DATASET')
    expect(crop.selection.value).toEqual(outside)
  })

  it('does not cut anything while the dataset bounds are unknown, and picks up late bounds', () => {
    const known = ref<CropBounds | null>(null)
    const crop = useCropSelection(known)
    crop.setBounds({ ...dataset, minX: 0, maxX: 10 })
    expect(crop.bounds.value).toEqual({ ...dataset, minX: 0, maxX: 10 })

    known.value = dataset
    expect(crop.bounds.value).toBeNull()
    expect(crop.error.value).toBe('OUTSIDE_DATASET')
  })

  it('clears the region and the corners', () => {
    const crop = useCropSelection(dataset)
    crop.startPicking()
    crop.addCorner({ x: 500010, y: 2000010, z: 101 })
    crop.clear()
    crop.setBounds(dataset)
    crop.clear()
    expect(crop.corners.value).toEqual([])
    expect(crop.selection.value).toBeNull()
    expect(crop.bounds.value).toBeNull()
    expect(crop.error.value).toBeNull()
  })

  it('starts a new region on a pick after a finished one', () => {
    const crop = useCropSelection(dataset)
    crop.startPicking()
    crop.addCorner({ x: 500010, y: 2000010, z: 101 })
    crop.addCorner({ x: 500050, y: 2000050, z: 101 })
    crop.startPicking()
    crop.addCorner({ x: 500060, y: 2000060, z: 101 })
    expect(crop.corners.value).toHaveLength(1)
    expect(crop.bounds.value).toBeNull()
  })
})
