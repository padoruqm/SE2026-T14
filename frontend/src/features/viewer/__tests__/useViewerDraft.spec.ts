import { effectScope, ref, type EffectScope } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useViewerDraft } from '../useViewerDraft'
import { DraftApiError, type DraftApi, type ViewerDraft } from '../viewerDraftApi'

const original: ViewerDraft = { revision: 0, state: { pointSize: 1, colorMode: 'rgb' } }
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
let scope: EffectScope
function setup(api: DraftApi) {
  const id = ref('pc_alpha')
  scope = effectScope()
  const draft = scope.run(() => useViewerDraft(id, api))!
  return { id, ...draft }
}
function fakeApi() {
  return {
    load: vi.fn<DraftApi['load']>().mockResolvedValue(original),
    save: vi.fn<DraftApi['save']>().mockImplementation(async (_id, command) => ({
      revision: command.expectedRevision + 1,
      state: command.state,
    })),
  }
}
beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  scope?.stop()
  vi.useRealTimers()
})

describe('viewer draft: requirement-derived UI contracts', () => {
  it('T23 never reports saved when a successful acknowledgement mismatches the command', async () => {
    const api = fakeApi()
    api.save.mockResolvedValueOnce({ revision: 1, state: { pointSize: 1, colorMode: 'rgb' } })
    const draft = setup(api)
    await flushPromises()
    draft.pointSize.value = 3
    await vi.advanceTimersByTimeAsync(300)
    expect(draft.status.value).toBe('error')
    expect(draft.pointSize.value).toBe(3)
  })

  it('T24 retains retry availability if the user edits after a network failure', async () => {
    const api = fakeApi()
    api.save.mockRejectedValueOnce(new TypeError('lost ack'))
    const draft = setup(api)
    await flushPromises()
    draft.pointSize.value = 2
    await vi.advanceTimersByTimeAsync(300)
    draft.pointSize.value = 4
    expect(draft.status.value).toBe('error')
    await draft.retry()
    await vi.advanceTimersByTimeAsync(300)
    expect(api.save).toHaveBeenCalledTimes(3)
    expect(api.save.mock.calls[2]![1]).toMatchObject({
      expectedRevision: 1,
      state: { pointSize: 4, colorMode: 'rgb' },
    })
    expect(draft.status.value).toBe('saved')
  })
  it('T15 waits 300 ms and automatically saves the final valid edit', async () => {
    const api = fakeApi()
    const draft = setup(api)
    await flushPromises()
    draft.pointSize.value = 2
    await vi.advanceTimersByTimeAsync(299)
    expect(api.save).not.toHaveBeenCalled()
    draft.pointSize.value = 3
    await vi.advanceTimersByTimeAsync(300)
    expect(api.save).toHaveBeenCalledTimes(1)
    expect(api.save.mock.calls[0]![1].state).toEqual({ pointSize: 3, colorMode: 'rgb' })
    expect(draft.status.value).toBe('saved')
  })

  it('T16 keeps newer edits while an old save is in flight, then saves only latest', async () => {
    const api = fakeApi()
    const first = deferred<ViewerDraft>()
    api.save.mockReturnValueOnce(first.promise)
    const draft = setup(api)
    await flushPromises()
    draft.pointSize.value = 2
    await vi.advanceTimersByTimeAsync(300)
    draft.pointSize.value = 3
    draft.pointSize.value = 4
    first.resolve({ revision: 1, state: { pointSize: 2, colorMode: 'rgb' } })
    await flushPromises()
    expect(draft.pointSize.value).toBe(4)
    expect(draft.status.value).toBe('dirty')
    await vi.advanceTimersByTimeAsync(300)
    expect(api.save).toHaveBeenCalledTimes(2)
    expect(api.save.mock.calls[1]![1]).toMatchObject({
      expectedRevision: 1,
      state: { pointSize: 4, colorMode: 'rgb' },
    })
    expect(draft.status.value).toBe('saved')
  })

  it('T17 retries the exact operation after a lost acknowledgement', async () => {
    const api = fakeApi()
    api.save.mockRejectedValueOnce(new TypeError('connection lost after commit'))
    const draft = setup(api)
    await flushPromises()
    draft.colorMode.value = 'intensity'
    await vi.advanceTimersByTimeAsync(300)
    expect(draft.status.value).toBe('error')
    const firstCommand = api.save.mock.calls[0]![1]
    await draft.retry()
    expect(api.save.mock.calls[1]![1]).toEqual(firstCommand)
    expect(draft.colorMode.value).toBe('intensity')
    expect(draft.status.value).toBe('saved')
  })

  it('T18 cannot autosave defaults before the saved draft finishes loading', async () => {
    const api = fakeApi()
    const loading = deferred<ViewerDraft>()
    api.load.mockReturnValueOnce(loading.promise)
    const draft = setup(api)
    expect(draft.ready.value).toBe(false)
    draft.pointSize.value = 2
    await vi.advanceTimersByTimeAsync(300)
    expect(api.save).not.toHaveBeenCalled()
    loading.resolve({ revision: 7, state: { pointSize: 4, colorMode: 'elevation' } })
    await flushPromises()
    expect(draft.pointSize.value).toBe(4)
    expect(draft.ready.value).toBe(true)
  })

  it('T19 ignores delayed load/save responses after changing dataset', async () => {
    const api = fakeApi()
    const oldLoad = deferred<ViewerDraft>()
    api.load.mockReturnValueOnce(oldLoad.promise)
    const draft = setup(api)
    draft.id.value = 'pc_beta'
    await flushPromises()
    oldLoad.resolve({ revision: 20, state: { pointSize: 5, colorMode: 'intensity' } })
    await flushPromises()
    expect(draft.pointSize.value).toBe(1)
    const oldSave = deferred<ViewerDraft>()
    api.save.mockReturnValueOnce(oldSave.promise)
    draft.pointSize.value = 2
    await vi.advanceTimersByTimeAsync(300)
    draft.id.value = 'pc_gamma'
    await flushPromises()
    oldSave.resolve({ revision: 1, state: { pointSize: 2, colorMode: 'rgb' } })
    await flushPromises()
    expect(draft.pointSize.value).toBe(1)
    expect(draft.status.value).toBe('idle')
  })

  it('T20 keeps local edits on conflict and never blindly retries them', async () => {
    const api = fakeApi()
    api.save.mockRejectedValueOnce(new DraftApiError(409, 'newer draft'))
    const draft = setup(api)
    await flushPromises()
    draft.pointSize.value = 3
    await vi.advanceTimersByTimeAsync(300)
    expect(draft.status.value).toBe('conflict')
    expect(draft.pointSize.value).toBe(3)
    await draft.retry()
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.save).toHaveBeenCalledTimes(1)
    api.load.mockResolvedValueOnce({ revision: 2, state: { pointSize: 5, colorMode: 'rgb' } })
    await draft.reload()
    expect(draft.pointSize.value).toBe(5)
  })

  it('T21 cancels timers/requests on dispose without reporting saved', async () => {
    const api = fakeApi()
    const draft = setup(api)
    await flushPromises()
    draft.pointSize.value = 2
    scope.stop()
    await vi.advanceTimersByTimeAsync(300)
    expect(api.save).not.toHaveBeenCalled()
    expect(api.load.mock.calls[0]![1].aborted).toBe(true)
    expect(draft.status.value).not.toBe('saved')
  })

  it('T22 retries a failed initial load instead of saving unverified defaults', async () => {
    const api = fakeApi()
    api.load.mockRejectedValueOnce(new TypeError('network down'))
    const draft = setup(api)
    await flushPromises()
    expect(draft.status.value).toBe('error')
    await draft.retry()
    expect(draft.ready.value).toBe(true)
    expect(api.save).not.toHaveBeenCalled()
  })
})
