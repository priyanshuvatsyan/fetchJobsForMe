import { useMemo } from 'react'
import { SORT_OPTIONS, isWithinRange, matchesJob, sortJobs } from '../utils/jobs'

/** Filter and sort the saved jobs. None of this asks the API for a new fetch. */
export function useJobFilters(jobs, filters) {
  return useMemo(() => {
    const option = SORT_OPTIONS.find((item) => item.value === filters.sort)
    const matched = jobs.filter(
      (job) => matchesJob(job, filters) && isWithinRange(job, filters.dateRange),
    )
    return sortJobs(matched, option)
  }, [jobs, filters])
}

export default useJobFilters
