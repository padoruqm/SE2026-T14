import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ViewerControls from '../ViewerControls.vue'

function mountControls() {
  return mount(ViewerControls, { props: { pointSize: 1, colorMode: 'rgb' } })
}

describe('ViewerControls', () => {
  it('emits the new point size', async () => {
    const wrapper = mountControls()

    await wrapper.get('input[type="range"]').setValue('3')

    expect(wrapper.emitted('update:pointSize')).toEqual([[3]])
  })

  it('emits the chosen color mode', async () => {
    const wrapper = mountControls()

    await wrapper.get('select').setValue('elevation')

    expect(wrapper.emitted('update:colorMode')).toEqual([['elevation']])
  })

  it('emits resetView when the button is clicked', async () => {
    const wrapper = mountControls()

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('resetView')).toHaveLength(1)
  })
})
