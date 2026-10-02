const BASE_URL = (import.meta.env.VITE_JOBS_API_URL || 'https://fetchjobsforme.onrender.com').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function toQueryString(params) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.set(key, String(value))
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function request(method, path, { params = {}, body, signal } = {}) {
  let response
  try {
    response = await fetch(`${BASE_URL}${path}${toQueryString(params)}`, {
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(
      `Cannot reach the jobs API at ${BASE_URL}. Start it with: python backend/Server/server.py`,
      0,
    )
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(payload?.error || `Request failed with status ${response.status}`, response.status)
  }
  return payload
}

export const getJson = (path, options) => request('GET', path, options)
export const postJson = (path, body, options = {}) => request('POST', path, { ...options, body })
export const putJson = (path, body, options = {}) => request('PUT', path, { ...options, body })
export const deleteJson = (path, options) => request('DELETE', path, options)

export { BASE_URL }
