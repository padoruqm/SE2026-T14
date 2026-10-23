import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadApiBaseUrl(): Promise<string> {
  vi.resetModules()
  const config = await import('./config')
  return config.apiBaseUrl
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('apiBaseUrl', () => {
  it('uses the same origin by default in production', async () => {
    vi.stubEnv('PROD', true)

    await expect(loadApiBaseUrl()).resolves.toBe('')
  })

  it('uses the local backend by default in development', async () => {
    vi.stubEnv('PROD', false)

    await expect(loadApiBaseUrl()).resolves.toBe('http://127.0.0.1:8000')
  })

  it('uses the configured API base URL when provided', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test')

    await expect(loadApiBaseUrl()).resolves.toBe('https://api.example.test')
  })
})
