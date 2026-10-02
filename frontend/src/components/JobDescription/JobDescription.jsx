import './JobDescription.css'

/** The API returns plain text with one line per paragraph or bullet. */
function toBlocks(text) {
  return (text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

const isBullet = (line) => line.startsWith('-')

/** Short label lines such as "Responsibilities" or "What You'll Do:" that open a block. */
function isHeading(line, next) {
  if (isBullet(line) || line.length > 70 || /[.,;]$/.test(line)) return false
  if (line.endsWith(':')) return true
  return Boolean(next) && (isBullet(next) || next.length > line.length * 2)
}

const Section = ({ title, text }) => {
  const blocks = toBlocks(text)
  if (!blocks.length) return null

  return (
    <section className="job-description-section">
      <h4 className="job-description-title">{title}</h4>
      {blocks.map((line, index) =>
        isBullet(line) ? (
          <p className="job-description-bullet" key={index}>
            <span aria-hidden="true">•</span>
            {line.replace(/^-\s*/, '')}
          </p>
        ) : isHeading(line, blocks[index + 1]) ? (
          <p className="job-description-heading" key={index}>
            {line}
          </p>
        ) : (
          <p className="job-description-text" key={index}>
            {line}
          </p>
        ),
      )}
    </section>
  )
}

const Stats = ({ openings, applicants }) => {
  const items = [
    ['Openings', openings],
    ['Applicants', applicants],
  ].filter(([, value]) => value)
  if (!items.length) return null
  return (
    <div className="job-description-stats">
      {items.map(([label, value]) => (
        <p key={label} className="job-description-stat">
          <span>{label}</span>
          <strong>{value}</strong>
        </p>
      ))}
    </div>
  )
}

const Poster = ({ name, email }) => {
  if (!name && !email) return null
  return (
    <section className="job-description-section">
      <h4 className="job-description-title">Posted by</h4>
      {name ? <p className="job-description-text">{name}</p> : null}
      {email ? <p className="job-description-text">{email}</p> : null}
    </section>
  )
}

const JobDescription = ({
  aboutCompany,
  jobDescription,
  openings = '',
  applicants = '',
  postedBy = '',
  posterEmail = '',
}) => (
  <div className="job-description">
    <Stats openings={openings} applicants={applicants} />
    <Section title="About company" text={aboutCompany} />
    <Poster name={postedBy} email={posterEmail} />
    <Section title="Job description" text={jobDescription} />
  </div>
)

export default JobDescription
