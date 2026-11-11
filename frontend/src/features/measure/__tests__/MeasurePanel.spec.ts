import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import MeasurePanel from '../MeasurePanel.vue'
import { measureDistance, type Vec3 } from '../measurement'

const from = { x: 500000, y: 2000000, z: 100 }
const to = { x: 500003, y: 2000004, z: 112 }

interface Props {
  active: boolean
  coordinates: Vec3 | null
  measurement: ReturnType<typeof measureDistance> | null
  confirmingClear: boolean
  crs: string | null
}

function panel(props: Partial<Props> = {}, attachTo?: HTMLElement) {
  return mount(MeasurePanel, {
    props: {
      active: true,
      coordinates: null,
      measurement: null,
      confirmingClear: false,
      crs: 'EPSG:32648',
      ...props,
    },
    attachTo,
  })
}

function buttonLabels(wrapper: ReturnType<typeof panel>) {
  return wrapper.findAll('button').map((button) => button.text())
}

describe('MeasurePanel', () => {
  it('has a toggle that reports whether measuring is on', async () => {
    const off = panel({ active: false })
    expect(off.get('button').text()).toBe('Measure')
    expect(off.get('button').attributes('aria-pressed')).toBe('false')

    const on = panel({ active: true })
    expect(on.get('button').text()).toBe('Stop measuring')
    expect(on.get('button').attributes('aria-pressed')).toBe('true')

    await off.get('button').trigger('click')
    expect(off.emitted('toggle')).toHaveLength(1)
  })

  it('tells the user what to do while there is nothing picked', () => {
    const wrapper = panel({ active: true })

    expect(wrapper.text()).toContain('Click a point in the viewer')
    expect(buttonLabels(wrapper)).toEqual(['Stop measuring'])
  })

  it('shows nothing extra while the tool is off', () => {
    const wrapper = panel({ active: false })

    expect(wrapper.text()).not.toContain('Click a point')
  })

  it('shows X, Y and Z of a single point', () => {
    const wrapper = panel({ coordinates: { x: 500001.25, y: 2000002.5, z: 100.75 } })

    const text = wrapper.get('dl').text()
    expect(text).toContain('500001.250')
    expect(text).toContain('2000002.500')
    expect(text).toContain('100.750')
    expect(wrapper.text()).not.toContain('Click a point')
  })

  it('shows the distance, its horizontal and vertical parts and both points', () => {
    const wrapper = panel({ measurement: measureDistance(from, to) })

    const text = wrapper.get('[role="status"]').text()
    expect(text).toContain('Distance')
    expect(text).toContain('13.000 m')
    expect(text).toContain('5.000 m')
    expect(text).toContain('12.000 m')
    expect(text).toContain('500000.000, 2000000.000, 100.000')
    expect(text).toContain('500003.000, 2000004.000, 112.000')
  })

  it('says units when the CRS does not say what they are', () => {
    const unknown = panel({ measurement: measureDistance(from, to), crs: null })
    const odd = panel({ measurement: measureDistance(from, to), crs: 'EPSG:2154' })

    expect(unknown.text()).toContain('13.000 units')
    expect(odd.text()).toContain('13.000 units')
  })

  it('refuses a distance for angular coordinates and explains why', () => {
    const wrapper = panel({
      crs: 'EPSG:4326',
      measurement: measureDistance({ x: 105.1, y: 21.2, z: 10 }, { x: 105.2, y: 21.3, z: 10 }),
    })

    const text = wrapper.text()
    expect(text).toContain('angular coordinates')
    expect(text).not.toContain('Distance')
    expect(text).toContain('105.1000000, 21.2000000, 10.0000000')
  })

  it('shows angular coordinates of a single point with enough decimals', () => {
    const wrapper = panel({ crs: 'EPSG:4326', coordinates: { x: 105.123456789, y: 21.5, z: 0 } })

    expect(wrapper.get('dl').text()).toContain('105.1234568')
  })

  it('offers to clear only when something is measured', async () => {
    expect(buttonLabels(panel())).not.toContain('Clear measurement')

    const wrapper = panel({ coordinates: from })
    expect(buttonLabels(wrapper)).toContain('Clear measurement')

    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('requestClear')).toHaveLength(1)
  })

  it('asks before deleting and says the point cloud is not changed', () => {
    const wrapper = panel({ coordinates: from, confirmingClear: true })

    const group = wrapper.get('[role="group"]')
    expect(group.text()).toContain('Delete this measurement?')
    expect(group.text()).toContain('The point cloud is not changed')
    expect(buttonLabels(wrapper)).toEqual(['Stop measuring', 'Delete', 'Keep'])
  })

  it('emits confirm or cancel from the two answers', async () => {
    const wrapper = panel({ coordinates: from, confirmingClear: true })

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Delete')!
      .trigger('click')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Keep')!
      .trigger('click')

    expect(wrapper.emitted('confirmClear')).toHaveLength(1)
    expect(wrapper.emitted('cancelClear')).toHaveLength(1)
  })

  it('moves keyboard focus to the safe answer when the question appears', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const wrapper = panel({ coordinates: from }, host)

    await wrapper.setProps({ confirmingClear: true })
    await flushPromises()

    expect(document.activeElement?.textContent?.trim()).toBe('Keep')
    wrapper.unmount()
    host.remove()
  })
})
