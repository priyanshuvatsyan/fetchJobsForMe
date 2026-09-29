const BASE_URL = (import.meta.env.VITE_JOBS_API_URL || 'http://127.0.0.1:8001').replace(/\/$/, '')

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

export async function getJson(path, { params = {}, signal } = {}) {
  let response
  try {
    response = await fetch(`${BASE_URL}${path}${toQueryString(params)}`, {
      signal,
      headers: { Accept: 'application/json' },
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

export { BASE_URL }
