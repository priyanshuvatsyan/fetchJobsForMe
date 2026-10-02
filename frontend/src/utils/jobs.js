/**
 * Job helpers shared by the jobs page.
 *
 * Salary and experience parsing mirror the ordering rules in backend/Server/server.py
 * so a list sorted in the browser matches `--sort` in the terminal.
 */

export const DATE_RANGES = {
  any: { label: 'Any time', days: null },
  today: { label: 'Today', days: 1 },
  week: { label: 'Last 7 days', days: 7 },
  month: { label: 'Last 15 days', days: 15 },
}

export const SORT_OPTIONS = [
  { value: 'date_desc', label: 'Newest first', field: 'date', descending: true },
  { value: 'date_asc', label: 'Oldest first', field: 'date', descending: false },
  { value: 'salary_desc', label: 'Salary: high to low', field: 'salary', descending: true },
  { value: 'salary_asc', label: 'Salary: low to high', field: 'salary', descending: false },
  { value: 'exp_asc', label: 'Experience: low to high', field: 'exp', descending: false },
  { value: 'exp_desc', label: 'Experience: high to low', field: 'exp', descending: true },
]

const WORK_MODES = ['remote', 'hybrid', 'on-site', 'onsite', 'in-office']

export function normalizeJob(record, index = 0) {
  const description = record.description || {}
  return {
    id: record.link || `${record.company}-${record.role}-${index}`,
    portal: record.portal || '',
    portalKey: record.portalKey || '',
    company: record.company || '',
    role: record.role || '',
    experience: record.experience || '',
    skills: (record.skill || '')
      .split(',')
      .map((skill) => skill.trim())
      .filter(Boolean),
    salary: record.salary || '',
    postedAt: record['added on'] || '',
    savedAt: record['saved at'] || '',
    location: record.location || '',
    aboutCompany: description['about company'] || '',
    jobDescription: description['job description'] || '',
    openings: description.openings || '',
    applicants: description.applicants || '',
    link: record.link || '',
  }
}

/** Inverse of normalizeJob: the record shape the API stores. */
export function toRecord(job) {
  return {
    portal: job.portal,
    portalKey: job.portalKey,
    company: job.company,
    role: job.role,
    experience: job.experience,
    skill: job.skills.join(', '),
    salary: job.salary,
    'added on': job.postedAt,
    location: job.location,
    description: {
      'about company': job.aboutCompany,
      'job description': job.jobDescription,
      ...(job.openings ? { openings: job.openings } : {}),
      ...(job.applicants ? { applicants: job.applicants } : {}),
    },
    link: job.link,
  }
}

export function initials(name) {
  const words = (name || '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}

export function workMode(location) {
  const found = WORK_MODES.find((mode) => (location || '').toLowerCase().includes(mode))
  if (!found) return ''
  if (found === 'onsite' || found === 'on-site') return 'On-site'
  if (found === 'in-office') return 'In-office'
  return found.charAt(0).toUpperCase() + found.slice(1)
}

/** The API sends UTC "YYYY-MM-DD HH:MM:SS". */
export function parsePostedAt(value) {
  if (!value) return null
  const stamp = Date.parse(`${value.replace(' ', 'T')}Z`)
  return Number.isNaN(stamp) ? null : new Date(stamp)
}

export function formatPostedAt(value) {
  const date = parsePostedAt(value)
  if (!date) return ''
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days} days ago`
  const months = Math.floor(days / 30)
  return months === 1 ? '1 month ago' : `${months} months ago`
}

/** Local date and time, for example "29 Sep 2026, 11:42 AM". */
export function formatPostedDateTime(value) {
  const date = parsePostedAt(value)
  if (!date) return ''
  return date.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

function amount(token) {
  if (/^\d{1,3}(\.\d{3})+$/.test(token)) return Number(token.replace(/\./g, ''))
  if (/^\d{1,3}(,\d{3})+$/.test(token)) return Number(token.replace(/,/g, ''))
  if (token.includes(',') && token.includes('.')) {
    const normalized =
      token.lastIndexOf(',') > token.lastIndexOf('.')
        ? token.replace(/\./g, '').replace(',', '.')
        : token.replace(/,/g, '')
    return Number(normalized)
  }
  return Number(token.replace(/,/g, ''))
}

export function salaryValue(text) {
  if (!text) return null
  const values = []
  for (const match of text.matchAll(/(\d[\d.,]*)\s*([kK])?/g)) {
    const token = match[1].replace(/[.,]+$/, '')
    if (!token) continue
    const parsed = amount(token)
    if (Number.isNaN(parsed)) continue
    values.push(match[2] ? parsed * 1000 : parsed)
  }
  return values.length ? Math.max(...values) : null
}

const EXPERIENCE_LEVELS = [
  ['intern', 0],
  ['junior', 1],
  ['bachelor', 2],
  ['master', 4],
  ['phd', 6],
  ['senior', 5],
  ['lead', 6],
  ['staff', 8],
  ['principal', 10],
  ['director', 12],
  ['head', 12],
]

export function experienceValue(text) {
  if (!text) return null
  const years = text.match(/(\d+(?:\.\d+)?)\s*(?:\+|plus)?(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?\s*years?/i)
  if (years) return Number(years[1])
  const folded = text.toLowerCase()
  const level = EXPERIENCE_LEVELS.find(([word]) => folded.includes(word))
  return level ? level[1] : null
}

function sortValue(job, field) {
  if (field === 'salary') return salaryValue(job.salary)
  if (field === 'exp') return experienceValue(job.experience)
  const date = parsePostedAt(job.postedAt)
  return date ? date.getTime() : null
}

/** Jobs without a value for the sort field always sit at the bottom. */
export function sortJobs(jobs, option) {
  if (!option) return jobs
  return [...jobs].sort((left, right) => {
    const a = sortValue(left, option.field)
    const b = sortValue(right, option.field)
    if (a === null && b === null) return 0
    if (a === null) return 1
    if (b === null) return -1
    return option.descending ? b - a : a - b
  })
}

export function isWithinRange(job, rangeKey) {
  const days = DATE_RANGES[rangeKey]?.days
  if (!days) return true
  const date = parsePostedAt(job.postedAt)
  if (!date) return false
  return Date.now() - date.getTime() <= days * 86_400_000
}

function includes(haystack, needle) {
  const text = needle.trim().toLowerCase()
  return !text || haystack.toLowerCase().includes(text)
}

/** Stable portal id from the API. Display names such as "4 Day Week" are not compared. */
export function portalKeyOf(job, portals = []) {
  if (job.portalKey) return job.portalKey
  const label = (job.portal || '').toLowerCase()
  const match = portals.find((portal) => (portal.label || '').toLowerCase() === label)
  return match?.key || ''
}

/** Search, location, portal, and company tokens applied to the saved job list. */
export function matchesJob(job, { query = '', where = '', source = 'all', boards = '' }, portals = []) {
  const haystack = `${job.role} ${job.company} ${job.location}`
  if (!includes(haystack, query) || !includes(haystack, where)) return false
  if (source !== 'all' && portalKeyOf(job, portals) !== source) return false
  const tokens = boards
    .split(',')
    .map((token) => token.trim().toLowerCase().replace(/[^a-z0-9]/g, ''))
    .filter(Boolean)
  if (!tokens.length) return true
  const company = job.company.toLowerCase().replace(/[^a-z0-9]/g, '')
  return tokens.some((token) => company.includes(token))
}

/** Why a non-empty result set is hidden, so a portal filter is not described as a date filter. */
export function unmatchedReason(jobs, filters, portals = []) {
  const matched = jobs.filter((job) => matchesJob(job, filters, portals))
  const inRange = matched.filter((job) => isWithinRange(job, filters.dateRange))
  if (inRange.length) return null
  if (!jobs.length) {
    return { title: 'No jobs matched', message: 'Try a different keyword, portal, or company.' }
  }
  if (filters.source && filters.source !== 'all') {
    const fromPortal = jobs.filter((job) => portalKeyOf(job, portals) === filters.source)
    if (!fromPortal.length) {
      const label = portals.find((portal) => portal.key === filters.source)?.label || 'this portal'
      return {
        title: `No jobs from ${label}`,
        message: 'Nothing from this portal is in the current results.',
      }
    }
  }
  const hiddenByDate = matched.filter((job) => !isWithinRange(job, filters.dateRange)).length
  if (filters.dateRange !== 'any' && hiddenByDate > 0) {
    const noun = hiddenByDate === 1 ? 'job is' : 'jobs are'
    return {
      title: 'No jobs in this date range',
      message: `${hiddenByDate} ${noun} older than the selected range.`,
    }
  }
  return { title: 'No jobs matched', message: 'Try a different keyword, portal, or company.' }
}
