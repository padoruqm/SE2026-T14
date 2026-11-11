import { describe, expect, it } from 'vitest'

import { useMeasure } from '../useMeasure'

const a = { x: 0, y: 0, z: 0 }
const b = { x: 3, y: 4, z: 12 }
const c = { x: 10, y: 10, z: 10 }

function started() {
  const measure = useMeasure()
  measure.start()
  return measure
}

describe('useMeasure', () => {
  it('starts inactive with nothing measured', () => {
    const measure = useMeasure()

    expect(measure.active.value).toBe(false)
    expect(measure.points.value).toEqual([])
    expect(measure.coordinates.value).toBeNull()
    expect(measure.measurement.value).toBeNull()
  })

  it('ignores picks while the tool is off', () => {
    const measure = useMeasure()

    measure.addPoint(a)

    expect(measure.points.value).toEqual([])
  })

  it('shows the coordinates of a single point', () => {
    const measure = started()

    measure.addPoint({ x: 500001.25, y: 2000002.5, z: 100.75 })

    expect(measure.coordinates.value).toEqual({ x: 500001.25, y: 2000002.5, z: 100.75 })
    expect(measure.measurement.value).toBeNull()
  })

  it('measures the distance once two points are picked', () => {
    const measure = started()

    measure.addPoint(a)
    measure.addPoint(b)

    expect(measure.coordinates.value).toBeNull()
    expect(measure.measurement.value?.distance).toBe(13)
    expect(measure.measurement.value?.horizontal).toBe(5)
    expect(measure.measurement.value?.vertical).toBe(12)
  })

  it('starts a new measurement on the third pick', () => {
    const measure = started()
    measure.addPoint(a)
    measure.addPoint(b)

    measure.addPoint(c)

    expect(measure.points.value).toEqual([c])
    expect(measure.coordinates.value).toEqual(c)
    expect(measure.measurement.value).toBeNull()
  })

  it('keeps copies, so changing the picked object later changes nothing', () => {
    const measure = started()
    const picked = { x: 1, y: 2, z: 3 }

    measure.addPoint(picked)
    picked.x = 99

    expect(measure.points.value[0]).toEqual({ x: 1, y: 2, z: 3 })
  })

  it('ignores a pick with non-finite coordinates', () => {
    const measure = started()

    measure.addPoint({ x: NaN, y: 0, z: 0 })
    measure.addPoint({ x: 0, y: Infinity, z: 0 })

    expect(measure.points.value).toEqual([])
  })

  it('keeps the measurement when the tool is switched off', () => {
    const measure = started()
    measure.addPoint(a)
    measure.addPoint(b)

    measure.stop()

    expect(measure.active.value).toBe(false)
    expect(measure.measurement.value?.distance).toBe(13)
  })
})

describe('clearing', () => {
  it('asks for confirmation and keeps the measurement until it is given', () => {
    const measure = started()
    measure.addPoint(a)
    measure.addPoint(b)

    measure.requestClear()

    expect(measure.confirmingClear.value).toBe(true)
    expect(measure.measurement.value?.distance).toBe(13)
  })

  it('removes the measurement once confirmed', () => {
    const measure = started()
    measure.addPoint(a)
    measure.addPoint(b)
    measure.requestClear()

    measure.confirmClear()

    expect(measure.points.value).toEqual([])
    expect(measure.measurement.value).toBeNull()
    expect(measure.confirmingClear.value).toBe(false)
  })

  it('keeps the measurement when the confirmation is cancelled', () => {
    const measure = started()
    measure.addPoint(a)
    measure.requestClear()

    measure.cancelClear()

    expect(measure.points.value).toEqual([a])
    expect(measure.confirmingClear.value).toBe(false)
  })

  it('does not ask to clear when there is nothing to clear', () => {
    const measure = started()

    measure.requestClear()

    expect(measure.confirmingClear.value).toBe(false)
  })

  it('cannot clear without first asking', () => {
    const measure = started()
    measure.addPoint(a)

    measure.confirmClear()

    expect(measure.points.value).toEqual([a])
  })

  it('ignores picks while waiting for the answer', () => {
    const measure = started()
    measure.addPoint(a)
    measure.requestClear()

    measure.addPoint(b)

    expect(measure.points.value).toEqual([a])
  })

  it('drops a pending confirmation when the tool is switched off', () => {
    const measure = started()
    measure.addPoint(a)
    measure.requestClear()

    measure.stop()

    expect(measure.confirmingClear.value).toBe(false)
    expect(measure.points.value).toEqual([a])
  })
})
