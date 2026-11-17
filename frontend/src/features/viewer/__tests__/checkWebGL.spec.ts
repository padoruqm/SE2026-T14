import { afterEach, describe, expect, it, vi } from 'vitest'

import { checkWebGL } from '../checkWebGL'

function stubGetContext(implementation: (type: string) => unknown) {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    implementation as HTMLCanvasElement['getContext'],
  )
}

function glContext() {
  return { getExtension: () => null }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('checkWebGL', () => {
  it('is true when a WebGL 2 context can be created', () => {
    stubGetContext((type) => (type === 'webgl2' ? glContext() : null))

    expect(checkWebGL()).toBe(true)
  })

  it('falls back to WebGL 1', () => {
    stubGetContext((type) => (type === 'webgl' ? glContext() : null))

    expect(checkWebGL()).toBe(true)
  })

  it('is false when no context can be created', () => {
    stubGetContext(() => null)

    expect(checkWebGL()).toBe(false)
  })

  it('is false when creating a context throws', () => {
    stubGetContext(() => {
      throw new Error('blocked')
    })

    expect(checkWebGL()).toBe(false)
  })

  it('releases the context it created', () => {
    const loseContext = vi.fn<() => void>()
    stubGetContext(() => ({ getExtension: () => ({ loseContext }) }))

    checkWebGL()

    expect(loseContext).toHaveBeenCalledOnce()
  })
})
