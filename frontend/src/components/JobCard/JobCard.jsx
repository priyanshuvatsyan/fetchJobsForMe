import { useId, useState } from 'react'
import Button from '../Button/Button'
import JobDescription from '../JobDescription/JobDescription'
import { formatPostedAt, formatPostedDateTime, initials, workMode } from '../../utils/jobs'
import './JobCard.css'

const PALETTE = [
  'linear-gradient(140deg, #7c3aed, #4338ca)',
  'linear-gradient(140deg, #2563eb, #0ea5e9)',
  'linear-gradient(140deg, #059669, #10b981)',
  'linear-gradient(140deg, #d97706, #f59e0b)',
  'linear-gradient(140deg, #db2777, #a21caf)',
  'linear-gradient(140deg, #dc2626, #f97316)',
]

function paletteFor(name) {
  let total = 0
  for (const character of name || '') total += character.charCodeAt(0)
  return PALETTE[total % PALETTE.length]
}

/** Company tile with initials, used when a portal gives us no logo. */
const Avatar = ({ name, size = 'md' }) => (
  <span
    className={`avatar avatar-${size}`}
    style={{ backgroundImage: paletteFor(name) }}
    aria-hidden="true"
  >
    {initials(name)}
  </span>
)

/** Small pill used for portal, work mode, experience, salary and skills. */
const Badge = ({ tone = 'neutral', icon = null, children, className = '' }) => {
  if (children === null || children === undefined || children === '') return null
  return (
    <span className={`badge badge-${tone} ${className}`.trim()}>
      {icon ? <span className="badge-icon">{icon}</span> : null}
      {children}
    </span>
  )
}

/** Single-choice row of buttons, used for the posted-date range. */
export const SegmentedControl = ({ label, value, onChange, options }) => (
  <div className="segmented">
    {label ? <span className="segmented-label">{label}</span> : null}
    <div className="segmented-track" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`segmented-option ${option.value === value ? 'is-active' : ''}`.trim()}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  </div>
)

const StarIcon = ({ filled }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
    <path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z" />
  </svg>
)

const JobCard = ({ job, defaultExpanded = false, saved = false, onToggleSave }) => {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const panelId = useId()
  const mode = workMode(job.location)
  const posted = formatPostedAt(job.postedAt)
  const postedAt = formatPostedDateTime(job.postedAt)
  const hasDescription = Boolean(job.aboutCompany || job.jobDescription)

  const toggle = () => setExpanded((open) => !open)

  const onHeaderKeyDown = (event) => {
    if (!hasDescription) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggle()
    }
  }

  return (
    <article className={`job-card ${expanded ? 'is-expanded' : ''}`.trim()}>
      <div
        className="job-card-header"
        role={hasDescription ? 'button' : undefined}
        tabIndex={hasDescription ? 0 : undefined}
        aria-expanded={hasDescription ? expanded : undefined}
        aria-controls={hasDescription ? panelId : undefined}
        onClick={hasDescription ? toggle : undefined}
        onKeyDown={onHeaderKeyDown}
      >
        <Avatar name={job.company} />

        <div className="job-card-identity">
          <span className="job-card-kicker">Job</span>
          <h3 className="job-card-role">
            {job.link ? (
              <a
                className="job-card-role-link"
                href={job.link}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                {job.role}
              </a>
            ) : (
              job.role
            )}
          </h3>
          <p className="job-card-company">{job.company}</p>
        </div>

        <div className="job-card-actions" onClick={(event) => event.stopPropagation()}>
          {job.portal ? <Badge tone="accent">{job.portal}</Badge> : null}
          {job.apply || job.link ? (
            <Button href={job.apply || job.link} size="sm" aria-label={`Apply for ${job.role} at ${job.company}`}>
              Apply
              <span aria-hidden="true">↗</span>
            </Button>
          ) : null}
          {onToggleSave && job.link ? (
            <button
              type="button"
              className={`job-card-save ${saved ? 'is-saved' : ''}`.trim()}
              onClick={() => onToggleSave(job)}
              aria-pressed={saved}
              aria-label={saved ? `Remove ${job.role} from saved jobs` : `Save ${job.role}`}
              title={saved ? 'Remove from saved jobs' : 'Save job'}
            >
              <StarIcon filled={saved} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="job-card-meta">
        {job.location ? <span className="job-card-location">{job.location}</span> : null}
        {mode ? <Badge tone="info">{mode}</Badge> : null}
        {job.experience ? <Badge tone="neutral">{job.experience}</Badge> : null}
        {job.salary ? <Badge tone="success">{job.salary}</Badge> : null}
        {posted ? (
          <span className="job-card-posted">
            <span>{posted}</span>
            {postedAt ? <time className="job-card-posted-at" dateTime={job.postedAt}>{postedAt}</time> : null}
          </span>
        ) : null}
      </div>

      {job.skills.length ? (
        <div className="job-card-skills">
          {job.skills.slice(0, 6).map((skill) => (
            <Badge key={skill} tone="neutral">
              {skill}
            </Badge>
          ))}
          {job.skills.length > 6 ? <Badge tone="neutral">{`+${job.skills.length - 6}`}</Badge> : null}
        </div>
      ) : null}

      {hasDescription && expanded ? (
        <div className="job-card-panel" id={panelId}>
          <JobDescription
            aboutCompany={job.aboutCompany}
            jobDescription={job.jobDescription}
            openings={job.openings}
            applicants={job.applicants}
            postedBy={job.postedBy}
            posterEmail={job.posterEmail}
          />
        </div>
      ) : null}
    </article>
  )
}

export default JobCard
