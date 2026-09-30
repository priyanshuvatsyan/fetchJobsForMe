import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchJobs, stopJobs } from '../api/jobs'

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
    if (refresh) setData((current) => ({ ...current, loading: true }))

    const pull = (isRefresh) => {
      fetchJobs({ refresh: isRefresh }, controller.signal)
        .then((result) => {
          if (gen !== generation.current || controller.signal.aborted) return
          setData(result)
          if (result.loading) {
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

  const stop = useCallback(() => {
    const gen = generation.current + 1
    generation.current = gen
    request.current?.abort()
    clearTimeout(timer.current)
    const controller = new AbortController()
    request.current = controller
    stopJobs(controller.signal)
      .then((result) => {
        if (gen !== generation.current || controller.signal.aborted) return
        setData(result)
        setStatus('success')
        setError(null)
        timer.current = setTimeout(() => {
          fetchJobs({ refresh: false }, controller.signal)
            .then((latest) => {
              if (gen !== generation.current || controller.signal.aborted) return
              setData({ ...latest, loading: false })
            })
            .catch((cause) => {
              if (cause?.name === 'AbortError') return
            })
        }, 1200)
      })
      .catch((cause) => {
        if (gen !== generation.current || controller.signal.aborted || cause.name === 'AbortError') return
        setError(cause)
        setStatus('error')
      })
  }, [])

  return { ...data, status, error, reload, stop }
}

export default useJobs
