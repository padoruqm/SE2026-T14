import { describe, expect, it } from 'vitest'

import { boundsRows, formatCoordinate, formatPointCount } from '../formatMetadata'

describe('formatPointCount', () => {
  it('groups thousands', () => {
    expect(formatPointCount(1250000)).toBe('1,250,000')
  })

  it('keeps small and zero counts readable', () => {
    expect(formatPointCount(0)).toBe('0')
    expect(formatPointCount(42)).toBe('42')
  })
})

describe('formatCoordinate', () => {
  it('uses three decimals so millimetre precision is visible', () => {
    expect(formatCoordinate(100)).toBe('100.000')
    expect(formatCoordinate(-1.23456)).toBe('-1.235')
  })
})

describe('boundsRows', () => {
  it('lists min, max and extent for each axis', () => {
    const rows = boundsRows({
      minX: 100,
      minY: 200,
      minZ: -1.5,
      maxX: 180.5,
      maxY: 260.25,
      maxZ: 42.7,
    })

    expect(rows).toEqual([
      { axis: 'X', min: '100.000', max: '180.500', extent: '80.500' },
      { axis: 'Y', min: '200.000', max: '260.250', extent: '60.250' },
      { axis: 'Z', min: '-1.500', max: '42.700', extent: '44.200' },
    ])
  })
})
