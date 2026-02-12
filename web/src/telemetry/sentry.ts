import { flush, init } from '@sentry/react'

type BrowserMeta = {
  dsn: string
  environment: string
  release?: string
  sampleRate: number
}

const REDACTED_HEADERS = ['authorization', 'x-api-key', 'cookie', 'set-cookie']

const parseRate = (value: string | undefined, fallback: number): number => {
  if (value === undefined || value.trim() === '') {
    return fallback
  }
  const parsed = Number.parseFloat(value)
  if (Number.isNaN(parsed)) {
    return fallback
  }
  return Math.min(1, Math.max(0, parsed))
}

const sanitizeHeaders = (headers: Record<string, string> | undefined): void => {
  if (!headers) {
    return
  }

  for (const [name] of Object.entries(headers)) {
    const key = name.toLowerCase()
    if (REDACTED_HEADERS.includes(key)) {
      headers[name] = '[REDACTED]'
    } else if (key.includes('token') || key.includes('secret')) {
      headers[name] = '[REDACTED]'
    }
  }
}

export const initSentry = (meta?: Partial<BrowserMeta>): void => {
  const dsn = import.meta.env.VITE_SENTRY_DSN || meta?.dsn
  if (!dsn) {
    return
  }

  const sampleRate = parseRate(
    meta?.sampleRate !== undefined ? String(meta.sampleRate) : undefined,
    parseRate(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE, 0.05),
  )

  const defaults: BrowserMeta = {
    dsn,
    environment:
      meta?.environment ||
      import.meta.env.VITE_SENTRY_ENVIRONMENT ||
      import.meta.env.MODE ||
      'unknown',
    release:
      meta?.release ||
      import.meta.env.VITE_SENTRY_RELEASE ||
      import.meta.env.VITE_APP_VERSION,
    sampleRate,
  }

  init({
    dsn: defaults.dsn,
    environment: defaults.environment,
    release: defaults.release,
    integrations: [],
    tracesSampleRate: defaults.sampleRate,
    sendDefaultPii: false,
    beforeSend: (event) => {
      if (event.request?.headers) {
        sanitizeHeaders(event.request.headers as Record<string, string>)
      }
      return event
    },
  })
}

export const flushSentryEvents = (timeoutMs = 2000): Promise<boolean> => flush(timeoutMs)
