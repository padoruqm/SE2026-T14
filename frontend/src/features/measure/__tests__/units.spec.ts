import { describe, expect, it } from 'vitest'

import { distanceUnit } from '../units'

describe('distanceUnit', () => {
  it.each(['EPSG:32648', 'EPSG:32601', 'EPSG:32660', 'EPSG:32748', 'EPSG:3857', 'EPSG:4978'])(
    'treats %s as metres',
    (crs) => {
      expect(distanceUnit(crs)).toEqual({ label: 'm', geographic: false })
    },
  )

  it.each(['EPSG:4326', 'EPSG:4979', 'EPSG:4269', 'EPSG:4258'])(
    'treats %s as geographic',
    (crs) => {
      expect(distanceUnit(crs)).toEqual({ label: '°', geographic: true })
    },
  )

  it.each([null, '', 'unknown', 'EPSG:', 'EPSG:abc', 'EPSG:2154', 'EPSG:32600', 'EPSG:32661'])(
    'does not guess for %s',
    (crs) => {
      expect(distanceUnit(crs)).toEqual({ label: 'units', geographic: false })
    },
  )

  it('ignores case and surrounding spaces', () => {
    expect(distanceUnit('  epsg:32648 ')).toEqual({ label: 'm', geographic: false })
  })
})
