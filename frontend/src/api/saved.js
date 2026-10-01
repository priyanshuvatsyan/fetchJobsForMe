import { deleteJson, getJson, postJson } from './client'
import { normalizeJob, toRecord } from '../utils/jobs'

export async function fetchSavedJobs(signal) {
  const payload = await getJson('/api/saved', { signal })
  return (payload.jobs || []).map(normalizeJob)
}

export async function saveJob(job) {
  const payload = await postJson('/api/saved', { job: toRecord(job) })
  return normalizeJob(payload.job)
}

export async function unsaveJob(link) {
  await deleteJson('/api/saved', { params: { link } }).catch((error) => {
    if (error.status !== 404) throw error
  })
}

/** Job Discovery numbers, computed by the API from the jobs it already holds. */
export function fetchSummary(signal) {
  return getJson('/api/summary', { signal })
}
