import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { fetchSavedJobs, saveJob, unsaveJob } from '../api/saved'
import { auth } from '../firebase'

/**
 * Starred jobs, stored in Firebase under the signed-in user.
 * Toggling updates the list at once and rolls back if the request fails.
 */
export function useSavedJobs() {
  const [saved, setSaved] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const pending = useRef(new Set())

  useEffect(() => {
    const controller = new AbortController()
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (!user) {
        setSaved([])
        setError(null)
        setStatus('idle')
        return
      }
      fetchSavedJobs(controller.signal)
        .then((jobs) => {
          setSaved(jobs)
          setStatus('success')
        })
        .catch((cause) => {
          if (cause.name === 'AbortError' || cause.status === 401) return
          setError(cause)
          setStatus('error')
        })
    })
    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [])

  const savedLinks = useMemo(() => new Set(saved.map((job) => job.link)), [saved])

  const toggle = useCallback(
    async (job) => {
      if (!job.link || pending.current.has(job.link)) return
      pending.current.add(job.link)
      setError(null)
      const wasSaved = savedLinks.has(job.link)
      const previous = saved
      setSaved(wasSaved ? saved.filter((item) => item.link !== job.link) : [job, ...saved])
      try {
        if (wasSaved) {
          await unsaveJob(job.link)
        } else {
          const stored = await saveJob(job)
          setSaved((current) => current.map((item) => (item.link === stored.link ? stored : item)))
        }
      } catch (cause) {
        setSaved(previous)
        setError(cause)
      } finally {
        pending.current.delete(job.link)
      }
    },
    [saved, savedLinks],
  )

  return { saved, savedLinks, toggle, status, error }
}

export default useSavedJobs
