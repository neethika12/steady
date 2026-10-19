// Small fetch wrapper. All requests go to /api on the same origin
// (Vite proxies it in development, nginx in Docker).

export class ApiError extends Error {
  status: number
  code: string
  detail: unknown

  constructor(status: number, code: string, message: string, detail: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.detail = detail
  }
}

function messageFrom(status: number, body: unknown): { code: string; message: string } {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'message' in detail) {
    const d = detail as { code?: string; message: string }
    return { code: d.code ?? 'error', message: d.message }
  }
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI validation errors: [{loc, msg}]
    const first = detail[0] as { loc?: (string | number)[]; msg?: string }
    const field = first.loc?.filter((p) => p !== 'body').join(' → ')
    const msg = (first.msg ?? 'Invalid input').replace(/^Value error, /, '')
    return { code: 'validation', message: field ? `${field}: ${msg}` : msg }
  }
  if (typeof detail === 'string') return { code: 'error', message: detail }
  if (status >= 500) return { code: 'server', message: 'The server hit a problem. Your last change may not have been saved.' }
  return { code: 'error', message: `Request failed (${status}).` }
}

export async function api<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(0, 'network', "Couldn't reach the server. Check that the app is running, then try again.", null)
  }
  if (response.status === 204) return undefined as T
  let parsed: unknown = null
  try {
    parsed = await response.json()
  } catch {
    parsed = null
  }
  if (!response.ok) {
    const { code, message } = messageFrom(response.status, parsed)
    // Signed out (session expired, or logged out in another tab): show the log-in screen.
    if (response.status === 401 && code === 'auth_required') window.dispatchEvent(new Event('steady:auth-required'))
    throw new ApiError(response.status, code, message, (parsed as { detail?: unknown } | null)?.detail)
  }
  return parsed as T
}

export const get = <T,>(path: string, signal?: AbortSignal) => api<T>('GET', path, undefined, signal)
export const post = <T,>(path: string, body?: unknown) => api<T>('POST', path, body ?? {})
export const put = <T,>(path: string, body?: unknown) => api<T>('PUT', path, body ?? {})
export const patch = <T,>(path: string, body?: unknown) => api<T>('PATCH', path, body ?? {})
export const del = <T,>(path: string) => api<T>('DELETE', path)

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return 'Something went wrong.'
}

/** A fresh id for a create request. Re-sending the same id never creates a duplicate. */
export function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  // Fallback for non-secure contexts (e.g. opening the app via a LAN IP).
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}
