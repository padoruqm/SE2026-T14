import { describe, expect, it } from 'vitest'

import { createClient } from '../generated/client'
import { convertPointCloud, getJob, getPointCloud, uploadPointCloud } from '../generated'
import type { ErrorResponse, Job } from '../generated'

function clientReturning(status: number, body: unknown) {
  const requests: Request[] = []
  const client = createClient({
    baseUrl: 'http://mock.test',
    fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(new Request(input, init))
      return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    },
  })
  return { client, requests }
}

describe('generated API client', () => {
  it('exposes one function per contract operation', () => {
    for (const operation of [uploadPointCloud, getPointCloud, convertPointCloud, getJob]) {
      expect(operation).toBeTypeOf('function')
    }
  })

  it('fills path parameters and returns typed job data', async () => {
    const job: Job = {
      id: 'job_1',
      type: 'convert',
      state: 'running',
      progress: 40,
      resultId: null,
      error: null,
    }
    const { client, requests } = clientReturning(200, job)

    const result = await getJob({ client, path: { id: 'job_1' } })

    expect(requests[0]?.method).toBe('GET')
    expect(requests[0]?.url).toBe('http://mock.test/api/job/job_1')
    expect(result.data).toEqual(job)
  })

  it('surfaces the shared error schema', async () => {
    const error: ErrorResponse = {
      error: { code: 'NOT_FOUND', message: 'Not Found', requestId: 'req_1', details: {} },
    }
    const { client } = clientReturning(404, error)

    const result = await getPointCloud({ client, path: { id: 'missing' } })

    expect(result.error).toEqual(error)
  })

  it('posts the convert request as JSON', async () => {
    const { client, requests } = clientReturning(202, {})

    await convertPointCloud({ client, path: { id: 'pc_1' }, body: { force: true } })

    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.url).toBe('http://mock.test/api/pointcloud/pc_1/convert')
    expect(await requests[0]?.json()).toEqual({ force: true })
  })
})
