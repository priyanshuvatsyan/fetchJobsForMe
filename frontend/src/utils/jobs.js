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
  month: { label: 'Last 30 days', days: 30 },
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
    company: record.company || '',
    role: record.role || '',
    experience: record.experience || '',
    skills: (record.skill || '')
      .split(',')
      .map((skill) => skill.trim())
      .filter(Boolean),
    salary: record.salary || '',
    postedAt: record['added on'] || '',
    location: record.location || '',
    aboutCompany: description['about company'] || '',
    jobDescription: description['job description'] || '',
    link: record.link || '',
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

/** Search, location, portal, and company tokens applied to the saved job list. */
export function matchesJob(job, { query = '', where = '', source = 'all', boards = '' }) {
  const haystack = `${job.role} ${job.company} ${job.location}`
  if (!includes(haystack, query) || !includes(haystack, where)) return false
  if (source !== 'all' && job.portal.toLowerCase() !== source.toLowerCase()) return false
  const tokens = boards
    .split(',')
    .map((token) => token.trim().toLowerCase().replace(/[^a-z0-9]/g, ''))
    .filter(Boolean)
  if (!tokens.length) return true
  const company = job.company.toLowerCase().replace(/[^a-z0-9]/g, '')
  return tokens.some((token) => company.includes(token))
}

/** Keep the first `limit` jobs of each portal. Call this after sorting. */
export function capPerPortal(jobs, limit) {
  const size = Number(limit) || jobs.length
  const seen = new Map()
  return jobs.filter((job) => {
    const count = seen.get(job.portal) || 0
    if (count >= size) return false
    seen.set(job.portal, count + 1)
    return true
  })
}
