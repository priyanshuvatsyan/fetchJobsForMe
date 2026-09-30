import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchJobs, fetchLinkedInJobs } from '../api/jobs'

const EMPTY = {
  jobs: [],
  portals: [],
  credits: [],
  notes: [],
  linkedinSearchUrl: '',
  loading: false,
  fetchedAt: '',
}

/**
 * Read the saved jobs, or follow a live fetch. While portals are still
 * running the same request is polled so cards appear as each company returns.
 */
export function useJobs() {
  const [data, setData] = useState(EMPTY)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const request = useRef(null)
  const timer = useRef(null)
  const generation = useRef(0)

  const load = useCallback((refresh) => {
    const gen = generation.current + 1
    generation.current = gen
    request.current?.abort()
    clearTimeout(timer.current)
    const controller = new AbortController()
    request.current = controller
    setStatus('loading')
    setError(null)

    const pull = (isRefresh) => {
      Promise.all([
        fetchJobs({ refresh: isRefresh }, controller.signal),
        fetchLinkedInJobs({ refresh: isRefresh }, controller.signal),
      ])
        .then(([result, linkedin]) => {
          if (gen !== generation.current || controller.signal.aborted) return
          const seen = new Set()
          const jobs = []
          for (const job of [...result.jobs, ...linkedin.jobs]) {
            const key = job.link || job.id
            if (seen.has(key)) continue
            seen.add(key)
            jobs.push(job)
          }
          const loading = result.loading || linkedin.loading
          setData({ ...result, jobs, loading })
          if (loading) {
            timer.current = setTimeout(() => pull(false), 1000)
            return
          }
          setStatus('success')
        })
        .catch((cause) => {
          if (gen !== generation.current || controller.signal.aborted || cause.name === 'AbortError') return
          setError(cause)
          setStatus('error')
        })
    }

    pull(Boolean(refresh))
  }, [])

  useEffect(() => {
    load(false)
    return () => {
      generation.current += 1
      request.current?.abort()
      clearTimeout(timer.current)
    }
  }, [load])

  const reload = useCallback(() => load(true), [load])

  return { ...data, status, error, reload }
}

export default useJobs
