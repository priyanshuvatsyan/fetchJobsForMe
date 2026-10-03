import { getJson } from './client'
import { normalizeJob } from '../utils/jobs'

export async function stopJobs(signal) {
  const payload = await getJson('/api/jobs/stop', { signal })
  return {
    jobs: (payload.jobs || []).map(normalizeJob),
    portals: payload.portals || [],
    credits: payload.credits || [],
    notes: payload.notes || [],
    loading: false,
    fetchedAt: payload.fetchedAt || '',
  }
}

export async function fetchJobs({ refresh = false } = {}, signal) {
  const payload = await getJson('/api/jobs', {
    params: {
      refresh: refresh ? '1' : '',
    },
    signal,
  })
  return {
    jobs: (payload.jobs || []).map(normalizeJob),
    portals: payload.portals || [],
    credits: payload.credits || [],
    notes: payload.notes || [],
    loading: Boolean(payload.loading),
    fetchedAt: payload.fetchedAt || '',
  }
}
