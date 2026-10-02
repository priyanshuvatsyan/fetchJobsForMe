import { getJson, putJson } from './client'
import { auth } from '../firebase'

function uid() {
  const value = auth.currentUser?.uid
  if (!value) throw new Error('Sign in to manage job-search preferences')
  return value
}

export async function fetchPreferences(signal) {
  const payload = await getJson('/api/preferences', {
    params: { uid: uid() },
    signal,
  })
  return payload.preferences
}

export async function savePreferences(preferences, signal) {
  const payload = await putJson(
    '/api/preferences',
    { preferences },
    { params: { uid: uid() }, signal },
  )
  return payload.preferences
}
