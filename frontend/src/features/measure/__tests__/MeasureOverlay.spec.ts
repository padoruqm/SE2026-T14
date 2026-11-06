import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MeasureOverlay from '../MeasureOverlay.vue'
import type { Vec3 } from '../measurement'

interface Screen {
  x: number
  y: number
  visible: boolean
}

const first = { x: 1, y: 0, z: 0 }
const second = { x: 2, y: 0, z: 0 }

function overlay(
  screen: Record<number, Screen>,
  points: Vec3[] = [first, second],
  label: string | null = '13.000 m',
) {
  return mount(MeasureOverlay, {
    props: { points, version: 0, label, project: (point: Vec3) => screen[point.x]! },
  })
}

describe('MeasureOverlay', () => {
  it('draws a marker for each picked point at its screen position', () => {
    const wrapper = overlay({
      1: { x: 100, y: 200, visible: true },
      2: { x: 300, y: 250, visible: true },
    })

    const circles = wrapper.findAll('circle').map((c) => [c.attributes('cx'), c.attributes('cy')])
    expect(circles).toEqual([
      ['100', '200'],
      ['300', '250'],
    ])
  })

  it('joins two visible points with a line and labels it at the middle', () => {
    const wrapper = overlay({
      1: { x: 100, y: 200, visible: true },
      2: { x: 300, y: 250, visible: true },
    })

    const line = wrapper.get('line')
    expect([line.attributes('x1'), line.attributes('y1')]).toEqual(['100', '200'])
    expect([line.attributes('x2'), line.attributes('y2')]).toEqual(['300', '250'])
    expect(wrapper.get('text').text()).toBe('13.000 m')
    expect(wrapper.get('text').attributes('x')).toBe('200')
  })

  it('draws a single marker and no line for one point', () => {
    const wrapper = overlay({ 1: { x: 10, y: 20, visible: true } }, [first])

    expect(wrapper.findAll('circle')).toHaveLength(1)
    expect(wrapper.find('line').exists()).toBe(false)
    expect(wrapper.find('text').exists()).toBe(false)
  })

  it('hides a marker that is behind the camera or outside the view, and the line with it', () => {
    const wrapper = overlay({
      1: { x: 100, y: 200, visible: true },
      2: { x: NaN, y: NaN, visible: false },
    })

    expect(wrapper.findAll('circle')).toHaveLength(1)
    expect(wrapper.find('line').exists()).toBe(false)
    expect(wrapper.find('text').exists()).toBe(false)
  })

  it('has no label when none is given', () => {
    const wrapper = overlay(
      { 1: { x: 0, y: 0, visible: true }, 2: { x: 10, y: 10, visible: true } },
      [first, second],
      null,
    )

    expect(wrapper.find('line').exists()).toBe(true)
    expect(wrapper.find('text').exists()).toBe(false)
  })

  it('places the markers again when the view moves', async () => {
    let shift = 0
    const wrapper = mount(MeasureOverlay, {
      props: {
        points: [first],
        version: 0,
        label: null,
        project: () => ({ x: 100 + shift, y: 50, visible: true }),
      },
    })
    expect(wrapper.get('circle').attributes('cx')).toBe('100')

    shift = 25
    await wrapper.setProps({ version: 1 })

    expect(wrapper.get('circle').attributes('cx')).toBe('125')
  })

  it('is hidden from assistive technology, which reads the panel instead', () => {
    const wrapper = overlay({ 1: { x: 0, y: 0, visible: true } }, [first])

    expect(wrapper.get('svg').attributes('aria-hidden')).toBe('true')
  })
})
