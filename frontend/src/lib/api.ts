/** Thin fetch wrapper for the Django API: session cookies, CSRF, org header, error envelope. */

const BASE = '/api/v1'

export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors: FieldErrors
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, fieldErrors: FieldErrors = {}, requestId: string | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
    this.requestId = requestId
  }
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

let organizationId: string | null = null
export function setOrganizationId(id: string | null) {
  organizationId = id
}

let viewFocus: { section?: string; branch?: string } = {}
/** Top-bar focus: narrows reads (GET) to one section/branch. The server ignores it on writes and never widens access. */
export function setViewFocus(next: { section?: string; branch?: string }) {
  viewFocus = next
}
function addFocus(headers: Record<string, string>) {
  if (viewFocus.section) headers['X-Section-ID'] = viewFocus.section
  if (viewFocus.branch) headers['X-Branch-ID'] = viewFocus.branch
}

function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie('csrftoken')
  if (existing) return existing
  const response = await fetch(`${BASE}/auth/csrf/`, { credentials: 'same-origin' })
  const body = (await response.json()) as { csrfToken: string }
  return body.csrfToken
}

type Query = Record<string, string | number | undefined | null>

function buildUrl(path: string, query?: Query) {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value))
  }
  return url.pathname + url.search
}

interface RequestOptions {
  body?: unknown
  query?: Query
  idempotencyKey?: string
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (organizationId) headers['X-Organization-ID'] = organizationId
  if (method !== 'GET') {
    headers['X-CSRFToken'] = await ensureCsrfToken()
    headers['Content-Type'] = 'application/json'
  }
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey
  if (method === 'GET') addFocus(headers)

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      credentials: 'same-origin',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection and try again.')
  }

  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const error = payload?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'error',
      error?.message ?? 'The request could not be completed.',
      error?.field_errors ?? {},
      error?.request_id ?? response.headers.get('X-Request-ID'),
    )
  }
  return payload as T
}

/** POST multipart form data (file uploads). The browser sets the multipart boundary. */
async function upload<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', 'X-CSRFToken': await ensureCsrfToken() }
  if (organizationId) headers['X-Organization-ID'] = organizationId
  let response: Response
  try {
    response = await fetch(buildUrl(path), { method: 'POST', headers, credentials: 'same-origin', body: form })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection and try again.')
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const error = payload?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'error',
      error?.message ?? 'The upload failed.',
      error?.field_errors ?? {},
      error?.request_id ?? response.headers.get('X-Request-ID'),
    )
  }
  return payload as T
}

/** GET a file (e.g. a report export) and hand it to the browser as a download. */
async function download(path: string, query?: Query): Promise<string> {
  const headers: Record<string, string> = {}
  if (organizationId) headers['X-Organization-ID'] = organizationId
  addFocus(headers)
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), { headers, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection and try again.')
  }
  if (!response.ok) {
    const error = (await response.json().catch(() => null))?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'error',
      error?.message ?? 'The file could not be created.',
      error?.field_errors ?? {},
      error?.request_id ?? response.headers.get('X-Request-ID'),
    )
  }
  const name = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? 'download'
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
  return name
}

export const api = {
  download,
  upload,
  delete: <T>(path: string) => request<T>('DELETE', path),
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown, idempotencyKey?: string) => request<T>('POST', path, { body, idempotencyKey }),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, { body }),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, { body }),
}
