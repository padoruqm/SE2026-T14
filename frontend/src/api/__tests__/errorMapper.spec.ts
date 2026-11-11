import { describe, expect, it } from 'vitest'

import type { ErrorCode } from '@/api/generated'

import { mapError, type ErrorKind } from '../errorMapper'

function apiError(code: string, message = 'server text') {
  return { error: { code, message, requestId: 'req_1' } }
}

describe('mapError', () => {
  it.each<[ErrorCode, ErrorKind, boolean]>([
    ['BAD_REQUEST', 'validation', false],
    ['VALIDATION_ERROR', 'validation', false],
    ['FILE_TOO_LARGE', 'validation', false],
    ['UNSUPPORTED_FILE_TYPE', 'validation', false],
    ['INVALID_POINT_CLOUD', 'processing', false],
    ['CONFLICT', 'processing', false],
    ['NOT_FOUND', 'notFound', false],
    ['METHOD_NOT_ALLOWED', 'unexpected', true],
    ['INTERNAL_ERROR', 'unexpected', true],
  ])('maps %s to %s (retryable: %s)', (code, kind, retryable) => {
    const mapped = mapError(apiError(code))

    expect(mapped.kind).toBe(kind)
    expect(mapped.retryable).toBe(retryable)
    expect(mapped.message).not.toBe('')
  })

  it('treats a failed fetch as a retryable network error', () => {
    expect(mapError(new TypeError('Failed to fetch'))).toMatchObject({
      kind: 'network',
      retryable: true,
    })
  })

  it.each([undefined, null, 'oops', {}, { error: null }, { error: {} }, apiError('NEW_CODE')])(
    'treats %j as a retryable unexpected error',
    (error) => {
      expect(mapError(error)).toMatchObject({ kind: 'unexpected', retryable: true })
    },
  )

  it('does not look up inherited object keys as error codes', () => {
    expect(mapError(apiError('constructor')).kind).toBe('unexpected')
  })

  it('never shows the server message', () => {
    const mapped = mapError(apiError('INTERNAL_ERROR', 'Traceback in /srv/app/secret.py'))

    expect(mapped.message).not.toContain('secret')
  })
})
