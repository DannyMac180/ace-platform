import { afterEach, describe, expect, it, vi } from 'vitest'

import { flush, init } from '@sentry/react'
import { initSentry, flushSentryEvents } from './sentry'

vi.mock('@sentry/react', () => ({
  init: vi.fn(),
  flush: vi.fn(),
}))

describe('web sentry telemetry', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('is no-op when no DSN is provided', () => {
    initSentry()
    expect(init).not.toHaveBeenCalled()
  })

  it('initializes with provided metadata and redacts sensitive headers', () => {
    let beforeSend: ((event: unknown) => unknown) | undefined
    vi.mocked(init).mockImplementation((options: Record<string, unknown>) => {
      beforeSend = options.beforeSend as
        | ((event: unknown) => unknown)
        | undefined
    })

    initSentry({ dsn: 'https://example@sentry.io/1', sampleRate: 0.42 })

    expect(init).toHaveBeenCalledTimes(1)
    const options = vi.mocked(init).mock.calls[0]?.[0] as {
      tracesSampleRate: number
      environment: string
      release?: string
      sendDefaultPii: boolean
    }
    expect(options.tracesSampleRate).toBe(0.42)
    expect(options.environment).toBe('test')
    expect(options.sendDefaultPii).toBe(false)

    expect(typeof beforeSend).toBe('function')
    const event = {
      request: {
        headers: {
          Authorization: 'top-secret',
          'X-Api-Key': 'api-key',
          'x-custom': 'safe',
        },
      },
    }
    const result = beforeSend?.(event as unknown)
    expect(result).toEqual({
      request: {
        headers: {
          Authorization: '[REDACTED]',
          'X-Api-Key': '[REDACTED]',
          'x-custom': 'safe',
        },
      },
    })
  })

  it('forwards flush timeout to SDK flush', async () => {
    vi.mocked(flush).mockResolvedValue(true)
    await expect(flushSentryEvents(2500)).resolves.toBe(true)
    expect(flush).toHaveBeenCalledWith(2500)
  })
})
