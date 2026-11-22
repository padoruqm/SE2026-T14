import { getJob, type Job } from '@/api/generated'
import { apiBaseUrl } from '@/shared/config'

const FINISHED: ReadonlySet<Job['state']> = new Set(['succeeded', 'failed', 'cancelled'])

export type JobWaitFailure = 'timeout' | 'unreachable'

/** The job did not finish: it ran too long, or its status could not be read several times. */
export class JobWaitError extends Error {
  constructor(readonly reason: JobWaitFailure) {
    super(reason === 'timeout' ? 'The job took too long' : 'The job status could not be read')
  }
}

export interface WaitForJobOptions {
  signal: AbortSignal
  /** Called with every state seen while waiting, including the last one. */
  onUpdate?: (job: Job) => void
  intervalMs?: number
  maxDurationMs?: number
  /** A network error is retried; this many in a row give up. */
  maxConsecutiveErrors?: number
  fetchJob?: (id: string, signal: AbortSignal) => Promise<Job>
}

async function fetchJobFromApi(id: string, signal: AbortSignal): Promise<Job> {
  const result = await getJob({ baseUrl: apiBaseUrl, path: { id }, signal, throwOnError: true })
  return result.data
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason)
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(signal.reason)
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

export function isFinished(job: Job): boolean {
  return FINISHED.has(job.state)
}

/**
 * Poll a job until it succeeds, fails or is cancelled, and return that final job.
 * A failed job is returned, not thrown: the caller decides how to show it. Aborting
 * the signal stops polling and rejects with the abort reason.
 */
export async function waitForJob(job: Job, options: WaitForJobOptions): Promise<Job> {
  const {
    signal,
    onUpdate,
    intervalMs = 1000,
    maxDurationMs = 5 * 60 * 1000,
    maxConsecutiveErrors = 3,
    fetchJob = fetchJobFromApi,
  } = options
  const startedAt = Date.now()
  let current = job
  let errors = 0
  onUpdate?.(current)

  while (!isFinished(current)) {
    if (Date.now() - startedAt >= maxDurationMs) throw new JobWaitError('timeout')
    await sleep(intervalMs, signal)
    try {
      current = await fetchJob(current.id, signal)
      errors = 0
      onUpdate?.(current)
    } catch (caught) {
      if (signal.aborted) throw caught
      if (!(caught instanceof TypeError)) throw caught
      errors += 1
      if (errors >= maxConsecutiveErrors) throw new JobWaitError('unreachable')
    }
  }
  return current
}
