import { getJson } from './client'
import { normalizeJob } from '../utils/jobs'

export const ALL_PORTALS = 'all'

export async function fetchJobs({ refresh = false } = {}, signal) {
  const payload = await getJson('/api/jobs', {
    params: { refresh: refresh ? '1' : '' },
    signal,
  })
  return {
    jobs: (payload.jobs || []).map(normalizeJob),
    portals: payload.portals || [],
    credits: payload.credits || [],
    notes: payload.notes || [],
    linkedinSearchUrl: payload.linkedinSearchUrl || '',
    loading: Boolean(payload.loading),
    fetchedAt: payload.fetchedAt || '',
  }
}

/** LinkedIn is stored in its own file and fetched beside the other portals. */
export async function fetchLinkedInJobs({ refresh = false } = {}, signal) {
  const payload = await getJson('/api/linkedin', {
    params: { refresh: refresh ? '1' : '' },
    signal,
  })
  return {
    jobs: (payload.jobs || []).map(normalizeJob),
    loading: Boolean(payload.loading),
  }
}

export async function fetchPortals(signal) {
  const payload = await getJson('/api/portals', { signal })
  return payload.portals || []
}
