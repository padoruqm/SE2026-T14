import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import UploadForm from '../UploadForm.vue'

const fetchMock = vi.fn<typeof fetch>()

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const uploaded = {
  id: 'pc_1',
  filename: 'scan.las',
  status: 'uploaded',
  metadata: { pointCount: null, bounds: null, crs: null },
}

function job(state: string, error: unknown = null) {
  return {
    id: 'job_1',
    type: 'convert',
    state,
    progress: null,
    resultId: state === 'succeeded' ? 'pc_1' : null,
    error,
  }
}

async function selectFile(wrapper: ReturnType<typeof mount>, name: string) {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [new File(['LASF'], name)] })
  await input.trigger('change')
}

async function mountWithFile(name = 'scan.las') {
  const wrapper = mount(UploadForm)
  await selectFile(wrapper, name)
  return wrapper
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('UploadForm', () => {
  it('shows a validation error and does not call the API for unsupported files', async () => {
    const wrapper = await mountWithFile('notes.txt')

    await wrapper.get('form').trigger('submit')

    expect(wrapper.get('[role="alert"]').text()).toBe('Only .las and .laz files are supported.')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows loading and disables the button while uploading', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')

    const button = wrapper.get('button[type="submit"]')
    expect(button.text()).toBe('Uploading…')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('shows queued, running, and completed conversion states', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('queued')))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('running')))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('succeeded')))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('Conversion queued…')

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('Conversion in progress…')

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toBe(
      'Conversion complete for scan.las (ID: pc_1).',
    )
    expect(fetchMock).toHaveBeenCalledTimes(4)
  })

  it.each([
    [413, 'FILE_TOO_LARGE', 'The uploaded file exceeds the maximum upload size'],
    [422, 'INVALID_POINT_CLOUD', 'The uploaded file is not a supported point cloud'],
  ])('shows the server message and a retry button on %i', async (status, code, message) => {
    fetchMock.mockResolvedValue(jsonResponse(status, { error: { code, message } }))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(message)
    expect(wrapper.get('button[type="button"]').text()).toBe('Try again')
  })

  it('shows conversion errors and allows retrying', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(
      jsonResponse(202, job('failed', { code: 'INVALID_POINT_CLOUD', message: 'Conversion failed.' })),
    )
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Conversion failed.')
    expect(wrapper.get('[role="status"]').text()).toBe('Conversion failed.')
    expect(wrapper.get('button[type="button"]').text()).toBe('Try again')
  })

  it('retries the same file after a network error without reloading', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('succeeded')))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not reach the server')

    await wrapper.get('button[type="button"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(3)
    const retriedBody = fetchMock.mock.calls[1]![1]!.body as FormData
    expect((retriedBody.get('file') as File).name).toBe('scan.las')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Conversion complete for scan.las')
  })

  it('aborts the upload when unmounted', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountWithFile()
    await wrapper.get('form').trigger('submit')

    wrapper.unmount()

    const signal = fetchMock.mock.calls[0]![1]!.signal as AbortSignal
    expect(signal.aborted).toBe(true)
  })
})
