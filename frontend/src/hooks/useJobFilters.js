import { useMemo } from 'react'
import { SORT_OPTIONS, isWithinRange, matchesJob, sortJobs } from '../utils/jobs'

/** Filter and sort the saved jobs. Portal identity is the API key, not the display name. */
export function useJobFilters(jobs, filters, portals = []) {
  return useMemo(() => {
    const option = SORT_OPTIONS.find((item) => item.value === filters.sort)
    const matched = jobs.filter(
      (job) => matchesJob(job, filters, portals) && isWithinRange(job, filters.dateRange),
    )
    return sortJobs(matched, option)
  }, [jobs, filters, portals])
}

export default useJobFilters
