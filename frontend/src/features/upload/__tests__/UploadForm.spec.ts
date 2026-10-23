import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'

import type { Job } from '@/api/generated'
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

function job(state: Job['state'], progress: Job['progress'] = null, error: Job['error'] = null) {
  return {
    id: 'job_1',
    type: 'convert',
    state,
    progress,
    resultId: state === 'succeeded' ? 'pc_1' : null,
    error,
  }
}

function requestAt(index: number): Request {
  return fetchMock.mock.calls[index]![0] as Request
}

async function selectFile(wrapper: ReturnType<typeof mount>, name: string) {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [new NodeFile(['LASF'], name)] })
  await input.trigger('change')
}

async function mountWithFile(name = 'scan.las') {
  const wrapper = mount(UploadForm)
  await selectFile(wrapper, name)
  return wrapper
}

async function advancePoll() {
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('Blob', NodeBlob)
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

  it('uses the generated API client to upload and start conversion', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('succeeded', 100)))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(requestAt(0).url).toBe('http://127.0.0.1:8000/api/upload')
    expect(requestAt(0).method).toBe('POST')
    expect((await requestAt(0).clone().formData()).get('file')).not.toBe('{}')
    expect(requestAt(1).url).toBe('http://127.0.0.1:8000/api/pointcloud/pc_1/convert')
    expect(requestAt(1).method).toBe('POST')
    expect(wrapper.get('[role="status"]').text()).toBe(
      'Conversion complete for scan.las (ID: pc_1).',
    )
  })

  it('shows queued, running, progress, and completed conversion states', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('queued')))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('running', 40)))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('succeeded', 100)))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('Conversion queued…')
    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()

    await advancePoll()
    expect(wrapper.get('[role="status"]').text()).toBe('Conversion in progress…')
    expect(wrapper.get('progress').attributes('value')).toBe('40')
    expect(wrapper.text()).toContain('40%')

    await advancePoll()
    expect(wrapper.get('[role="status"]').text()).toBe(
      'Conversion complete for scan.las (ID: pc_1).',
    )
    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(4)
  })

  it.each([
    [413, 'FILE_TOO_LARGE', 'The uploaded file exceeds the maximum upload size'],
    [422, 'INVALID_POINT_CLOUD', 'The uploaded file is not a supported point cloud'],
  ])('shows the server message and a retry button on %i', async (status, code, message) => {
    fetchMock.mockResolvedValue(
      jsonResponse(status, {
        error: { code, message, requestId: 'req_1', details: {} },
      }),
    )
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(message)
    expect(wrapper.get('button[type="button"]').text()).toBe('Try again')
  })

  it('shows a conversion error only once and retries conversion for the existing dataset', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        202,
        job('failed', null, { code: 'INVALID_POINT_CLOUD', message: 'Conversion failed.' }),
      ),
    )
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('queued')))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('succeeded', 100)))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Conversion failed.')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)

    await wrapper.get('button[type="button"]').trigger('click')
    await flushPromises()
    await advancePoll()

    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(requestAt(0).url).toContain('/api/upload')
    expect(requestAt(1).url).toContain('/api/pointcloud/pc_1/convert')
    expect(requestAt(2).url).toBe(requestAt(1).url)
    expect(requestAt(3).url).toContain('/api/job/job_1')
    expect(wrapper.get('[role="status"]').text()).toContain('Conversion complete')
  })

  it('retries an upload after a network error without reloading', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('succeeded', 100)))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not reach the server')

    await wrapper.get('button[type="button"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(requestAt(1).url).toContain('/api/upload')
    expect((await requestAt(1).clone().formData()).get('file')).not.toBe('{}')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Conversion complete for scan.las')
  })

  it('tolerates a transient poll network error and continues to show progress', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('queued')))
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('running', 60)))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('succeeded', 100)))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await advancePoll()
    expect(wrapper.get('[role="status"]').text()).toBe('Conversion queued…')

    await advancePoll()
    expect(wrapper.get('progress').attributes('value')).toBe('60')
    await advancePoll()

    expect(wrapper.get('[role="status"]').text()).toContain('Conversion complete')
    expect(fetchMock).toHaveBeenCalledTimes(5)
  })

  it('stops polling when the maximum conversion duration is exceeded', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(jsonResponse(201, uploaded))
    fetchMock.mockResolvedValueOnce(jsonResponse(202, job('queued')))
    fetchMock.mockResolvedValueOnce(jsonResponse(200, job('running', 20)))
    const wrapper = await mountWithFile()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    vi.setSystemTime(Date.now() + 5 * 60 * 1000)
    await advancePoll()

    expect(wrapper.get('[role="alert"]').text()).toContain('taking longer than expected')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('aborts the upload when unmounted', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountWithFile()
    await wrapper.get('form').trigger('submit')

    wrapper.unmount()

    expect(requestAt(0).signal.aborted).toBe(true)
  })
})
