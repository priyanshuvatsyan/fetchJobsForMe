import { getJson, postJson, putJson } from './client'

export async function fetchProfile(signal) {
  const payload = await getJson('/api/profile', { signal })
  return payload.profile
}

export async function saveProfile(profile, signal) {
  const payload = await putJson('/api/profile', { profile }, { signal })
  return payload.profile
}

function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error('Could not read the resume'))
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '')
    reader.readAsDataURL(file)
  })
}

export async function uploadResume(file, signal) {
  const content = await fileAsBase64(file)
  const payload = await postJson('/api/resume', { filename: file.name, content }, { signal })
  return payload
}
