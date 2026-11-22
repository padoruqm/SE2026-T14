import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import CropRequest from '../CropRequest.vue'
import type { CropRequestState } from '../useCropRequest'

const BOUNDS = { minX: 0, minY: 0, minZ: 0, maxX: 10, maxY: 10, maxZ: 5 }

interface Props {
  bounds: typeof BOUNDS | null
  state: CropRequestState
  progress: number | null
  resultId: string | null
  error: string | null
  retryable: boolean
}

function render(props: Partial<Props> = {}) {
  return mount(CropRequest, {
    props: {
      bounds: BOUNDS,
      state: 'idle',
      progress: null,
      resultId: null,
      error: null,
      retryable: false,
      ...props,
    },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })
}

function submitButton(wrapper: ReturnType<typeof render>) {
  return wrapper.findAll('button').find((b) => b.text() === 'Crop point cloud')!
}

describe('CropRequest', () => {
  it('sends the chosen format, LAZ by default', async () => {
    const wrapper = render()

    await submitButton(wrapper).trigger('click')
    await wrapper.get('select').setValue('las')
    await submitButton(wrapper).trigger('click')

    expect(wrapper.emitted('submit')).toEqual([['laz'], ['las']])
  })

  it('cannot send until there is a valid region, and says why', () => {
    const wrapper = render({ bounds: null })

    expect(submitButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Select a valid region to crop.')
  })

  it.each(['submitting', 'queued', 'running'] as const)(
    'cannot send again or change the format while %s',
    (state) => {
      const wrapper = render({ state })

      expect(submitButton(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.get('select').attributes('disabled')).toBeDefined()
    },
  )

  it('shows the job progress while cropping', () => {
    const wrapper = render({ state: 'running', progress: 40 })

    expect(wrapper.get('[role="status"]').text()).toContain('Cropping… 40%')
    expect(wrapper.get('progress').attributes('value')).toBe('40')
  })

  it('shows cropping without a percentage when the job has none', () => {
    const wrapper = render({ state: 'running', progress: null })

    expect(wrapper.get('[role="status"]').text()).toContain('Cropping…')
    expect(wrapper.find('progress').exists()).toBe(false)
  })

  it('links to the new point cloud when the crop is done', () => {
    const wrapper = render({ state: 'succeeded', resultId: 'pc_2' })

    expect(wrapper.text()).toContain('The original point cloud is unchanged.')
    expect(wrapper.get('a').attributes('href')).toBe('/viewer/pc_2')
  })

  it('shows the error and offers to try again when that can help', async () => {
    const wrapper = render({
      state: 'failed',
      error: 'The crop failed. Please try again.',
      retryable: true,
    })

    expect(wrapper.get('[role="alert"]').text()).toBe('The crop failed. Please try again.')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Try again')!
      .trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('does not offer to try again when it cannot help', () => {
    const wrapper = render({
      state: 'failed',
      error: 'This point cloud is not ready to crop yet.',
      retryable: false,
    })

    expect(wrapper.findAll('button').map((b) => b.text())).not.toContain('Try again')
  })

  it('lets a new crop be sent after a result or a failure', () => {
    expect(
      submitButton(render({ state: 'succeeded', resultId: 'pc_2' })).attributes('disabled'),
    ).toBeUndefined()
    expect(
      submitButton(render({ state: 'failed', error: 'x', retryable: true })).attributes('disabled'),
    ).toBeUndefined()
  })
})
