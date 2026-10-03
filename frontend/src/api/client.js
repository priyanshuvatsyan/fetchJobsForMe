import { signOut } from 'firebase/auth'
import { auth } from '../firebase'

const BASE_URL = (import.meta.env.VITE_JOBS_API_URL || 'https://fetchjobsforme.onrender.com').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const expiredSession = new Set([
  'auth/user-token-expired',
  'auth/user-disabled',
  'auth/invalid-user-token',
  'auth/user-not-found',
  'auth/invalid-credential',
])

let endingSession = false

async function endSession() {
  if (endingSession) return
  endingSession = true
  try {
    await signOut(auth)
  } catch {
    // The Firebase user is already gone.
  }
  if (!window.location.pathname.startsWith('/login')) {
    window.location.replace('/login')
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
  // Retrieve Firebase ID token if user is signed in
  const currentUser = auth.currentUser
  let token = null
  if (currentUser) {
    try {
      token = await currentUser.getIdToken()
    } catch (error) {
      if (expiredSession.has(error?.code)) await endSession()
      throw new ApiError('sign in is required', 401)
    }
  }

  let response
  try {
    response = await fetch(`${BASE_URL}${path}${toQueryString(params)}`, {
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
  if (response.status === 401 && token) {
    await endSession()
  }
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