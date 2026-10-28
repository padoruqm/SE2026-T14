import { describe, expect, it } from 'vitest'

import { distance, measureDistance } from '../measurement'

describe('distance', () => {
  it('is the straight-line distance in 3D', () => {
    expect(distance({ x: 0, y: 0, z: 0 }, { x: 1, y: 2, z: 2 })).toBe(3)
    expect(distance({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 })).toBe(5)
  })

  it('is zero for the same point', () => {
    expect(distance({ x: 5, y: -2, z: 9 }, { x: 5, y: -2, z: 9 })).toBe(0)
  })

  it('does not depend on the order of the points', () => {
    const a = { x: 1, y: 2, z: 3 }
    const b = { x: -4, y: 6, z: 0.5 }

    expect(distance(a, b)).toBe(distance(b, a))
  })

  it('handles negative coordinates', () => {
    expect(distance({ x: -1, y: -1, z: -1 }, { x: 1, y: 1, z: 1 })).toBeCloseTo(Math.sqrt(12), 12)
  })

  it('keeps millimetre precision at survey-scale coordinates', () => {
    const a = { x: 500000.123, y: 2000000.456, z: 12.5 }
    const b = { x: 500000.123, y: 2000000.457, z: 12.5 }

    expect(distance(a, b)).toBeCloseTo(0.001, 6)
  })

  it.each([NaN, Infinity, -Infinity])('rejects a point with %s', (bad) => {
    const good = { x: 0, y: 0, z: 0 }

    expect(() => distance({ x: bad, y: 0, z: 0 }, good)).toThrow(RangeError)
    expect(() => distance(good, { x: 0, y: bad, z: 0 })).toThrow(RangeError)
    expect(() => distance(good, { x: 0, y: 0, z: bad })).toThrow(RangeError)
  })
})

describe('measureDistance', () => {
  it('splits the distance into horizontal and vertical parts', () => {
    const result = measureDistance({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 12 })

    expect(result.distance).toBe(13)
    expect(result.horizontal).toBe(5)
    expect(result.vertical).toBe(12)
  })

  it('gives a negative vertical difference when the second point is lower', () => {
    const result = measureDistance({ x: 0, y: 0, z: 10 }, { x: 0, y: 0, z: 4 })

    expect(result.vertical).toBe(-6)
    expect(result.horizontal).toBe(0)
    expect(result.distance).toBe(6)
  })

  it('returns copies of the points and leaves its inputs unchanged', () => {
    const from = { x: 1, y: 2, z: 3 }
    const to = { x: 4, y: 5, z: 6 }

    const result = measureDistance(from, to)
    result.from.x = 99

    expect(from).toEqual({ x: 1, y: 2, z: 3 })
    expect(result.to).toEqual(to)
    expect(result.to).not.toBe(to)
  })

  it('rejects non-finite points', () => {
    expect(() => measureDistance({ x: NaN, y: 0, z: 0 }, { x: 0, y: 0, z: 0 })).toThrow(RangeError)
    expect(() => measureDistance({ x: 0, y: 0, z: 0 }, { x: 0, y: Infinity, z: 0 })).toThrow(
      RangeError,
    )
  })
})
