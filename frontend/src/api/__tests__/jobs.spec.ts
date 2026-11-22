import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Job } from '../generated'
import { JobWaitError, isFinished, waitForJob } from '../jobs'

function job(state: Job['state'], extra: Partial<Job> = {}): Job {
  return { id: 'job_1', type: 'crop', state, progress: null, resultId: null, error: null, ...extra }
}

function queue(...steps: Array<Job | Error>) {
  const fetchJob = vi.fn<(id: string, signal: AbortSignal) => Promise<Job>>()
  for (const step of steps) {
    if (step instanceof Error) fetchJob.mockRejectedValueOnce(step)
    else fetchJob.mockResolvedValueOnce(step)
  }
  return fetchJob
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('waitForJob', () => {
  it('polls until the job succeeds and returns the final job', async () => {
    const fetchJob = queue(job('running', { progress: 40 }), job('succeeded', { resultId: 'pc_2' }))
    const seen: Job['state'][] = []

    const done = waitForJob(job('queued'), {
      signal: new AbortController().signal,
      fetchJob,
      onUpdate: (j) => seen.push(j.state),
    })
    await vi.runAllTimersAsync()

    await expect(done).resolves.toMatchObject({ state: 'succeeded', resultId: 'pc_2' })
    expect(seen).toEqual(['queued', 'running', 'succeeded'])
    expect(fetchJob).toHaveBeenCalledTimes(2)
    expect(fetchJob.mock.calls[0]?.[0]).toBe('job_1')
  })

  it('returns a failed job instead of throwing', async () => {
    const failed = job('failed', { error: { code: 'INTERNAL_ERROR', message: 'boom' } })

    const done = waitForJob(job('running'), {
      signal: new AbortController().signal,
      fetchJob: queue(failed),
    })
    await vi.runAllTimersAsync()

    await expect(done).resolves.toEqual(failed)
  })

  it('does not poll a job that has already finished', async () => {
    const fetchJob = queue()

    await expect(
      waitForJob(job('succeeded'), { signal: new AbortController().signal, fetchJob }),
    ).resolves.toMatchObject({ state: 'succeeded' })
    expect(fetchJob).not.toHaveBeenCalled()
  })

  it('waits the interval between polls', async () => {
    const fetchJob = queue(job('running'), job('succeeded'))

    void waitForJob(job('queued'), {
      signal: new AbortController().signal,
      fetchJob,
      intervalMs: 1000,
    })
    await vi.advanceTimersByTimeAsync(999)
    expect(fetchJob).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('tolerates a few network errors in a row', async () => {
    const fetchJob = queue(new TypeError('offline'), new TypeError('offline'), job('succeeded'))

    const done = waitForJob(job('running'), { signal: new AbortController().signal, fetchJob })
    await vi.runAllTimersAsync()

    await expect(done).resolves.toMatchObject({ state: 'succeeded' })
  })

  it('gives up after too many network errors in a row', async () => {
    const fetchJob = queue(new TypeError('a'), new TypeError('b'), new TypeError('c'))

    const outcome = waitForJob(job('running'), {
      signal: new AbortController().signal,
      fetchJob,
    }).catch((error: unknown) => error)
    await vi.runAllTimersAsync()

    const error = await outcome
    expect(error).toBeInstanceOf(JobWaitError)
    expect(error).toMatchObject({ reason: 'unreachable' })
  })

  it('resets the error count after a successful poll', async () => {
    const fetchJob = queue(
      new TypeError('a'),
      new TypeError('b'),
      job('running'),
      new TypeError('c'),
      new TypeError('d'),
      job('succeeded'),
    )

    const done = waitForJob(job('running'), { signal: new AbortController().signal, fetchJob })
    await vi.runAllTimersAsync()

    await expect(done).resolves.toMatchObject({ state: 'succeeded' })
  })

  it('passes other errors straight through', async () => {
    const notFound = { error: { code: 'NOT_FOUND' } }
    const fetchJob = vi
      .fn<(id: string, signal: AbortSignal) => Promise<Job>>()
      .mockRejectedValue(notFound)

    const outcome = waitForJob(job('running'), {
      signal: new AbortController().signal,
      fetchJob,
    }).catch((error: unknown) => error)
    await vi.runAllTimersAsync()

    expect(await outcome).toBe(notFound)
  })

  it('gives up when the job runs past the maximum duration', async () => {
    const fetchJob = vi
      .fn<(id: string, signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValue(job('running'))

    const outcome = waitForJob(job('running'), {
      signal: new AbortController().signal,
      fetchJob,
      intervalMs: 1000,
      maxDurationMs: 5000,
    }).catch((error: unknown) => error)
    await vi.advanceTimersByTimeAsync(6000)

    expect(await outcome).toMatchObject({ reason: 'timeout' })
  })

  it('stops polling as soon as it is aborted', async () => {
    const controller = new AbortController()
    const fetchJob = vi
      .fn<(id: string, signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValue(job('running'))

    const outcome = waitForJob(job('running'), { signal: controller.signal, fetchJob }).then(
      () => 'finished',
      () => 'aborted',
    )
    await vi.advanceTimersByTimeAsync(2500)
    const calls = fetchJob.mock.calls.length
    controller.abort()
    expect(await outcome).toBe('aborted')
    await vi.advanceTimersByTimeAsync(10_000)

    expect(fetchJob.mock.calls.length).toBe(calls)
  })
})

describe('isFinished', () => {
  it.each([
    ['queued', false],
    ['running', false],
    ['succeeded', true],
    ['failed', true],
    ['cancelled', true],
  ] as const)('%s is finished: %s', (state, expected) => {
    expect(isFinished(job(state))).toBe(expected)
  })
})
