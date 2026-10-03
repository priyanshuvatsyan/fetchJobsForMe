import { useCallback, useEffect, useState } from 'react'
import { fetchProfile, saveProfile, uploadResume } from '../api/profile'

const EMPTY = {
  fullName: '',
  email: '',
  phone: '',
  headline: '',
  summary: '',
  currentTitle: '',
  currentCompany: '',
  totalExperience: '',
  noticePeriod: '',
  expectedSalary: '',
  salaryCurrency: 'INR',
  linkedin: '',
  github: '',
  portfolio: '',
  workAuthorization: '',
  education: '',
  experienceHistory: [],
  skills: [],
  targetRoles: [],
  preferredLocations: [],
  workModes: [],
  employmentTypes: [],
  openToWork: false,
  willingToRelocate: false,
  resume: null,
  completion: 0,
  updatedAt: '',
}

export default function useProfile() {
  const [profile, setProfile] = useState(EMPTY)
  const [status, setStatus] = useState('loading')
  const [message, setMessage] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchProfile(controller.signal)
      .then((data) => {
        setProfile({ ...EMPTY, ...data })
        setStatus('idle')
      })
      .catch((cause) => {
        if (cause.name === 'AbortError') return
        setError(cause)
        setStatus('error')
      })
    return () => controller.abort()
  }, [])

  const save = useCallback(async (next) => {
    setStatus('saving')
    setError(null)
    setMessage('')
    try {
      const data = await saveProfile(next)
      setProfile({ ...EMPTY, ...data })
      setMessage('Profile saved')
      setStatus('idle')
      return true
    } catch (cause) {
      setError(cause)
      setStatus('error')
      return false
    }
  }, [])

  const importResume = useCallback(async (file) => {
    setStatus('uploading')
    setError(null)
    setMessage('')
    try {
      const result = await uploadResume(file)
      setProfile({ ...EMPTY, ...result.profile })
      setMessage('Resume uploaded and profile updated. Review the extracted details.')
      setStatus('idle')
    } catch (cause) {
      setError(cause)
      setStatus('error')
    }
  }, [])

  return { profile, save, importResume, status, message, error }
}
