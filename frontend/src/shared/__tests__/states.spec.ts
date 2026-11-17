import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import EmptyState from '../EmptyState.vue'
import ErrorState from '../ErrorState.vue'
import LoadingState from '../LoadingState.vue'

describe('LoadingState', () => {
  it('announces the default and a custom label as a busy status', () => {
    expect(mount(LoadingState).get('[role="status"]').text()).toBe('Loading…')

    const custom = mount(LoadingState, { props: { label: 'Loading viewer…' } })

    expect(custom.get('[role="status"]').text()).toBe('Loading viewer…')
    expect(custom.get('[role="status"]').attributes('aria-busy')).toBe('true')
  })
})

describe('EmptyState', () => {
  it('shows the title, message and slot content', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Nothing here', message: 'Upload a file first.' },
      slots: { default: '<a href="/upload">Upload</a>' },
    })

    expect(wrapper.get('h2').text()).toBe('Nothing here')
    expect(wrapper.text()).toContain('Upload a file first.')
    expect(wrapper.find('a').exists()).toBe(true)
  })
})

describe('ErrorState', () => {
  it('shows the message as an alert without a retry button by default', () => {
    const wrapper = mount(ErrorState, { props: { message: 'It broke.' } })

    expect(wrapper.get('[role="alert"]').text()).toBe('It broke.')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('emits retry when the retry button is clicked', async () => {
    const wrapper = mount(ErrorState, {
      props: { title: 'Failed', message: 'It broke.', retryable: true },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.get('h2').text()).toBe('Failed')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('renders slot actions', () => {
    const wrapper = mount(ErrorState, {
      props: { message: 'It broke.' },
      slots: { default: '<a href="/upload">Back to upload</a>' },
    })

    expect(wrapper.get('a').text()).toBe('Back to upload')
  })
})
