import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import CropPanel from '../CropPanel.vue'
import type { CropBounds, CropError } from '../cropBounds'

const bounds: CropBounds = {
  minX: 500020,
  minY: 2000010,
  minZ: 100,
  maxX: 500080,
  maxY: 2000090,
  maxZ: 110,
}

interface Props {
  picking: boolean
  cornerCount: number
  selection: CropBounds | null
  bounds: CropBounds | null
  error: CropError | null
  crs: string | null
}

function panel(props: Partial<Props> = {}) {
  return mount(CropPanel, {
    props: {
      picking: false,
      cornerCount: 0,
      selection: null,
      bounds: null,
      error: null,
      crs: 'EPSG:32648',
      ...props,
    },
  })
}

describe('CropPanel', () => {
  it('has a toggle that reports whether picking is on', async () => {
    const wrapper = panel()
    const toggle = wrapper.get('button')
    expect(toggle.text()).toBe('Pick region')
    expect(toggle.attributes('aria-pressed')).toBe('false')

    await toggle.trigger('click')
    expect(wrapper.emitted('togglePicking')).toHaveLength(1)

    await wrapper.setProps({ picking: true })
    expect(wrapper.get('button').text()).toBe('Stop picking')
    expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
  })

  it('tells the user which corner to click', async () => {
    const wrapper = panel({ picking: true })
    expect(wrapper.text()).toContain('Click one corner')
    await wrapper.setProps({ cornerCount: 1 })
    expect(wrapper.text()).toContain('opposite corner')
  })

  it('shows the six values of the selection and the CRS', () => {
    const wrapper = panel({ selection: bounds, bounds })
    const values = wrapper.findAll('input').map((input) => input.element.value)
    expect(values).toEqual(['500020', '500080', '2000010', '2000090', '100', '110'])
    expect(wrapper.text()).toContain('world coordinates (EPSG:32648)')
    expect(wrapper.text()).toContain('500020, 2000010, 100')
    expect(wrapper.text()).toContain('500080, 2000090, 110')
  })

  it('sends the typed box when a value changes', async () => {
    const wrapper = panel({ selection: bounds, bounds })
    const minX = wrapper.findAll('input')[0]!
    await minX.setValue('500030')
    await minX.trigger('change')
    expect(wrapper.emitted('change')?.[0]).toEqual([{ ...bounds, minX: 500030 }])
  })

  it('waits until every field has a value before sending', async () => {
    const wrapper = panel()
    const [minX] = wrapper.findAll('input')
    await minX!.setValue('5')
    await minX!.trigger('change')
    expect(wrapper.emitted('change')).toBeUndefined()
  })

  it('shows an error as an alert and no result', () => {
    const wrapper = panel({ selection: bounds, error: 'OUTSIDE_DATASET' })
    expect(wrapper.get('[role="alert"]').text()).toContain('does not overlap')
    expect(wrapper.find('dl').exists()).toBe(false)
  })

  it('says when the region was cut to the point cloud', () => {
    const wrapper = panel({ selection: { ...bounds, minX: 499000 }, bounds })
    expect(wrapper.text()).toContain('cut to the point cloud')
  })

  it('offers Clear only when there is something to clear', async () => {
    const empty = panel()
    expect(empty.findAll('button').map((b) => b.text())).toEqual(['Pick region'])

    const filled = panel({ selection: bounds, bounds })
    const clear = filled.findAll('button').find((b) => b.text() === 'Clear')!
    await clear.trigger('click')
    expect(filled.emitted('clear')).toHaveLength(1)
  })
})
