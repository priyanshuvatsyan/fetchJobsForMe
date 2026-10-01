import './JobDescription.css'

/** The API returns plain text with one line per paragraph or bullet. */
function toBlocks(text) {
  return (text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

const Section = ({ title, text }) => {
  const blocks = toBlocks(text)
  if (!blocks.length) return null

  return (
    <section className="job-description-section">
      <h4 className="job-description-title">{title}</h4>
      {blocks.map((line, index) =>
        line.startsWith('-') ? (
          <p className="job-description-bullet" key={index}>
            <span aria-hidden="true">•</span>
            {line.replace(/^-\s*/, '')}
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

const JobDescription = ({ aboutCompany, jobDescription, openings = '', applicants = '' }) => (
  <div className="job-description">
    <Stats openings={openings} applicants={applicants} />
    <Section title="About company" text={aboutCompany} />
    <Section title="Job description" text={jobDescription} />
  </div>
)

export default JobDescription
