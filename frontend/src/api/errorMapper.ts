import type { ErrorCode } from '@/api/generated'

export type ErrorKind = 'validation' | 'network' | 'processing' | 'notFound' | 'unexpected'

export interface MappedError {
  kind: ErrorKind
  message: string
  retryable: boolean
}

const NETWORK: MappedError = {
  kind: 'network',
  message: 'Could not reach the server. Check your connection and try again.',
  retryable: true,
}

const UNEXPECTED: MappedError = {
  kind: 'unexpected',
  message: 'Something went wrong. Please try again.',
  retryable: true,
}

const BY_CODE: Record<ErrorCode, MappedError> = {
  BAD_REQUEST: {
    kind: 'validation',
    message: 'The request was not valid.',
    retryable: false,
  },
  VALIDATION_ERROR: {
    kind: 'validation',
    message: 'The request was not valid.',
    retryable: false,
  },
  FILE_TOO_LARGE: {
    kind: 'validation',
    message: 'The file is too large.',
    retryable: false,
  },
  UNSUPPORTED_FILE_TYPE: {
    kind: 'validation',
    message: 'This file type is not supported.',
    retryable: false,
  },
  METHOD_NOT_ALLOWED: UNEXPECTED,
  INVALID_POINT_CLOUD: {
    kind: 'processing',
    message: 'The file could not be read as a point cloud.',
    retryable: false,
  },
  CONFLICT: {
    kind: 'processing',
    message: 'This point cloud is already being processed or has been processed.',
    retryable: false,
  },
  NOT_FOUND: {
    kind: 'notFound',
    message: 'This point cloud was not found.',
    retryable: false,
  },
  INTERNAL_ERROR: UNEXPECTED,
}

function errorCode(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('error' in error)) return null
  const body = error.error
  if (typeof body !== 'object' || body === null || !('code' in body)) return null
  return typeof body.code === 'string' ? body.code : null
}

/**
 * Turn a failed request into a kind, a user-facing message and whether retrying can help.
 * Messages come from the stable `error.code`, never from server text, so no path, stack
 * trace or command can reach the screen.
 */
export function mapError(error: unknown): MappedError {
  if (error instanceof TypeError) return { ...NETWORK }
  const code = errorCode(error)
  const mapped =
    code !== null && Object.prototype.hasOwnProperty.call(BY_CODE, code)
      ? BY_CODE[code as ErrorCode]
      : null
  return { ...(mapped ?? UNEXPECTED) }
}
