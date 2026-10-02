import { auth, db } from '../firebase'
import { doc, getDoc, setDoc, serverTimestamp } from 'firebase/firestore'

function getPreferencesRef() {
  const user = auth.currentUser
  if (!user) throw new Error('Sign in to manage job-search preferences')
  return doc(db, 'users', user.uid, 'settings', 'preferences')
}

export async function fetchPreferences(signal) {
  if (!auth.currentUser) return {}

  const ref = getPreferencesRef()
  const snap = await getDoc(ref)

  if (!snap.exists()) {
    return {}
  }

  const data = snap.data()
  const resolvedApiKey = data.geminiApiKey || data.apiKey || ''

  return {
    ...data,
    apiKey: resolvedApiKey,
    geminiApiKey: resolvedApiKey,
    updatedAt: data.updatedAt?.toDate?.()?.toISOString() || data.updatedAt || '',
  }
}

export async function savePreferences(preferences, signal) {
  const ref = getPreferencesRef()

  const resolvedApiKey = preferences?.apiKey || preferences?.geminiApiKey || ''

  const payload = {
    roles: preferences?.roles || [],
    experience: preferences?.experience ?? null,
    posted: preferences?.posted || 'all',
    geminiApiKey: resolvedApiKey,
    updatedAt: serverTimestamp(),
  }

  await setDoc(ref, payload, { merge: true })

  return {
    ...payload,
    updatedAt: new Date().toISOString(),
  }
}