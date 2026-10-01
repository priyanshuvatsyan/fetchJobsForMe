import { useEffect, useRef, useState } from 'react'
import Callout from '../../components/Callout/Callout'
import useProfile from '../../hooks/useProfile'
import { formatPostedDateTime } from '../../utils/jobs'
import './SkillsProfile.css'

const WORK_MODES = ['Remote', 'Hybrid', 'On-site']
const EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract', 'Internship']

function cloneProfile(profile) {
  return {
    ...profile,
    skills: [...profile.skills],
    targetRoles: [...profile.targetRoles],
    preferredLocations: [...profile.preferredLocations],
    workModes: [...profile.workModes],
    employmentTypes: [...profile.employmentTypes],
  }
}

function display(value) {
  return value || 'Not added'
}

function chips(values) {
  return values.length ? values : null
}

function ProfileSection({ id, title, description, editing, onEdit, children }) {
  return (
    <section className="profile-section" aria-labelledby={`${id}-heading`}>
      <div className="profile-section-heading">
        <div>
          <h2 id={`${id}-heading`}>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {editing ? null : (
          <button type="button" className="profile-edit" onClick={onEdit}>
            Edit
          </button>
        )}
      </div>
      {children}
    </section>
  )
}

function TextField({ label, value, onChange, type = 'text', placeholder = '', wide = false }) {
  return (
    <label className={`profile-field${wide ? ' is-wide' : ''}`}>
      <span>{label}</span>
      <input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  )
}

function AreaField({ label, value, onChange, hint, rows = 5 }) {
  return (
    <label className="profile-field is-wide">
      <span>{label}</span>
      <textarea rows={rows} value={value} onChange={(event) => onChange(event.target.value)} />
      {hint ? <small>{hint}</small> : null}
    </label>
  )
}

function parseList(value) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function ListField({ name, label, values, onChange, placeholder, listsRef }) {
  const [draft, setDraft] = useState(values.join(', '))
  useEffect(() => {
    if (!listsRef) return undefined
    const readers = listsRef.current
    readers[name] = () => parseList(draft)
    return () => {
      delete readers[name]
    }
  }, [draft, listsRef, name])
  return (
    <label className="profile-field is-wide">
      <span>{label}</span>
      <input
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => onChange(parseList(draft))}
      />
      <small>Separate items with commas.</small>
    </label>
  )
}

function ChoiceGroup({ label, options, values, onChange }) {
  const selected = values || []
  return (
    <div className="profile-choices" role="group" aria-label={label}>
      <span className="profile-choices-label">{label}</span>
      <div>
        {options.map((option) => {
          const active = selected.includes(option)
          return (
            <button
              key={option}
              type="button"
              className={`profile-chip-toggle${active ? ' is-selected' : ''}`}
              aria-pressed={active}
              onClick={() => onChange(
                active ? selected.filter((item) => item !== option) : [...selected, option],
              )}
            >
              {option}
            </button>
          )
        })}
      </div>
      <small>Select all that apply.</small>
    </div>
  )
}

function ToggleTile({ title, detail, selected, onChange }) {
  return (
    <button
      type="button"
      className={`profile-tile${selected ? ' is-selected' : ''}`}
      aria-pressed={selected}
      onClick={() => onChange(!selected)}
    >
      <strong>{title}</strong>
      <small>{detail}</small>
    </button>
  )
}

function Facts({ items }) {
  return (
    <dl className="profile-facts">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd className={item.value ? '' : 'is-empty'}>{item.value || 'Not added'}</dd>
        </div>
      ))}
    </dl>
  )
}

function ChipList({ values, empty }) {
  if (!chips(values)) return <p className="profile-empty">{empty}</p>
  return (
    <ul className="profile-chips">
      {values.map((value) => <li key={value}>{value}</li>)}
    </ul>
  )
}

function Prose({ value, empty }) {
  if (!value) return <p className="profile-empty">{empty}</p>
  return <p className="profile-prose">{value}</p>
}

function SectionActions({ saving, onCancel, onSave }) {
  return (
    <div className="profile-actions">
      <button type="button" className="profile-cancel" onClick={onCancel} disabled={saving}>Cancel</button>
      <button type="button" className="profile-save" onClick={onSave} disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  )
}

function ResumeCard({ resume, status, onUpload }) {
  const inputRef = useRef(null)
  const uploading = status === 'uploading'
  const uploadedAt = resume?.uploadedAt ? formatPostedDateTime(resume.uploadedAt) : ''

  return (
    <aside className="resume-card">
      <div className={`resume-file-icon${resume ? ' has-file' : ''}`} aria-hidden="true">{resume ? '✓' : '↑'}</div>
      <p className="resume-eyebrow">RESUME</p>
      <h2>{resume ? 'Resume on file' : 'Upload your resume'}</h2>
      {resume ? (
        <div className="resume-current">
          <strong>{resume.filename}</strong>
          <span>{resume.type} · {(resume.size / 1024).toFixed(0)} KB</span>
          {uploadedAt ? <span>Updated {uploadedAt}</span> : null}
        </div>
      ) : (
        <p className="resume-copy">Import your headline, experience, education, skills, and contact details.</p>
      )}
      <input
        ref={inputRef}
        className="resume-input"
        type="file"
        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onUpload(file)
          event.target.value = ''
        }}
      />
      <button type="button" className="resume-upload" onClick={() => inputRef.current?.click()} disabled={uploading}>
        {uploading ? 'Reading resume…' : resume ? 'Update resume' : 'Upload resume'}
      </button>
      <p className="resume-help">PDF, DOCX, or TXT · maximum 8 MB</p>
    </aside>
  )
}

export default function SkillsProfile() {
  const { profile, save, importResume, status, message, error } = useProfile()
  const [editing, setEditing] = useState('')
  const [draft, setDraft] = useState(null)
  const listsRef = useRef({})
  const saving = status === 'saving'
  const form = draft || profile

  const begin = (section) => {
    setDraft(cloneProfile(profile))
    setEditing(section)
  }
  const cancel = () => {
    setDraft(null)
    setEditing('')
  }
  const setField = (field, value) => setDraft((current) => ({ ...current, [field]: value }))
  const commit = async () => {
    const lists = Object.fromEntries(
      Object.entries(listsRef.current).map(([field, read]) => [field, read()]),
    )
    const saved = await save({ ...draft, ...lists })
    if (saved) cancel()
  }
  const upload = async (file) => {
    cancel()
    await importResume(file)
  }

  return (
    <div className="profile-page">
      <header className="profile-heading">
        <div>
          <p>YOUR CAREER PROFILE</p>
          <h1>{profile.fullName || 'Skills & Profile'}</h1>
          <span>{profile.headline || 'Add a headline so recruiters know the role you want.'}</span>
        </div>
        <div className="profile-completion" aria-label={`${profile.completion}% profile complete`}>
          <strong>{profile.completion}%</strong>
          <span>complete</span>
        </div>
      </header>

      <section className="profile-metrics" aria-label="Profile overview">
        <div><span>Skills</span><strong>{profile.skills.length}</strong></div>
        <div><span>Target roles</span><strong>{profile.targetRoles.length}</strong></div>
        <div><span>Locations</span><strong>{profile.preferredLocations.length}</strong></div>
        <div><span>Resume</span><strong>{profile.resume ? 'Ready' : 'Missing'}</strong></div>
      </section>

      {error ? <Callout tone="error" title="Could not update profile"><p>{error.message}</p></Callout> : null}
      {message ? <p className="profile-note" role="status">{message}</p> : null}

      <div className="profile-layout">
        <main className="profile-form">
          <ProfileSection id="personal" title="Personal details" description="Name, contact, and the summary recruiters read first." editing={editing === 'personal'} onEdit={() => begin('personal')}>
            {editing === 'personal' ? (
              <>
                <div className="profile-grid">
                  <TextField label="Full name" value={form.fullName} onChange={(value) => setField('fullName', value)} />
                  <TextField label="Email" type="email" value={form.email} onChange={(value) => setField('email', value)} />
                  <TextField label="Phone" type="tel" value={form.phone} onChange={(value) => setField('phone', value)} />
                  <TextField label="Headline" value={form.headline} onChange={(value) => setField('headline', value)} placeholder="Senior Backend Engineer" />
                  <AreaField label="Profile summary" value={form.summary} onChange={(value) => setField('summary', value)} hint="A short overview of your specialization and impact." />
                </div>
                <SectionActions saving={saving} onCancel={cancel} onSave={commit} />
              </>
            ) : (
              <>
                <Facts items={[
                  { label: 'Email', value: profile.email },
                  { label: 'Phone', value: profile.phone },
                ]} />
                <Prose value={profile.summary} empty="Add a profile summary so recruiters can scan your background." />
              </>
            )}
          </ProfileSection>

          <ProfileSection id="skills" title="Key skills" description="The terms used to match you with roles." editing={editing === 'skills'} onEdit={() => begin('skills')}>
            {editing === 'skills' ? (
              <>
                <div className="profile-grid">
                  <ListField name="skills" listsRef={listsRef} label="Skills" values={form.skills} onChange={(value) => setField('skills', value)} placeholder="Python, React, AWS, SQL" />
                </div>
                <SectionActions saving={saving} onCancel={cancel} onSave={commit} />
              </>
            ) : (
              <ChipList values={profile.skills} empty="No skills added yet." />
            )}
          </ProfileSection>

          <ProfileSection id="employment" title="Employment" description="Current role, notice period, and work history." editing={editing === 'employment'} onEdit={() => begin('employment')}>
            {editing === 'employment' ? (
              <>
                <div className="profile-grid">
                  <TextField label="Current job title" value={form.currentTitle} onChange={(value) => setField('currentTitle', value)} />
                  <TextField label="Current company" value={form.currentCompany} onChange={(value) => setField('currentCompany', value)} />
                  <TextField label="Total experience" value={form.totalExperience} onChange={(value) => setField('totalExperience', value)} placeholder="4 years" />
                  <TextField label="Notice period" value={form.noticePeriod} onChange={(value) => setField('noticePeriod', value)} placeholder="30 days" />
                  <AreaField label="Work history" rows={8} value={form.experienceHistory} onChange={(value) => setField('experienceHistory', value)} hint="Company, title, dates, and what you delivered." />
                </div>
                <SectionActions saving={saving} onCancel={cancel} onSave={commit} />
              </>
            ) : (
              <>
                <div className="profile-role">
                  <strong>{profile.currentTitle || 'Current role not added'}</strong>
                  <span>{profile.currentCompany || 'Company not added'}</span>
                </div>
                <Facts items={[
                  { label: 'Total experience', value: profile.totalExperience },
                  { label: 'Notice period', value: profile.noticePeriod },
                ]} />
                <Prose value={profile.experienceHistory} empty="Add the companies and roles from your work history." />
              </>
            )}
          </ProfileSection>

          <ProfileSection id="education" title="Education" description="Degrees, institutions, and certifications." editing={editing === 'education'} onEdit={() => begin('education')}>
            {editing === 'education' ? (
              <>
                <div className="profile-grid">
                  <AreaField label="Education" rows={5} value={form.education} onChange={(value) => setField('education', value)} />
                </div>
                <SectionActions saving={saving} onCancel={cancel} onSave={commit} />
              </>
            ) : (
              <Prose value={profile.education} empty="Add your education and certifications." />
            )}
          </ProfileSection>

          <ProfileSection id="career" title="Career profile" description="The roles, locations, and terms you want next." editing={editing === 'career'} onEdit={() => begin('career')}>
            {editing === 'career' ? (
              <>
                <div className="profile-grid">
                  <ListField name="targetRoles" listsRef={listsRef} label="Target roles" values={form.targetRoles} onChange={(value) => setField('targetRoles', value)} placeholder="Backend Engineer, Platform Engineer" />
                  <ListField name="preferredLocations" listsRef={listsRef} label="Preferred locations" values={form.preferredLocations} onChange={(value) => setField('preferredLocations', value)} placeholder="Bengaluru, Pune, Remote" />
                  <ChoiceGroup label="Work mode" options={WORK_MODES} values={form.workModes} onChange={(value) => setField('workModes', value)} />
                  <ChoiceGroup label="Employment type" options={EMPLOYMENT_TYPES} values={form.employmentTypes} onChange={(value) => setField('employmentTypes', value)} />
                  <TextField label="Expected salary" value={form.expectedSalary} onChange={(value) => setField('expectedSalary', value)} />
                  <label className="profile-field">
                    <span>Salary currency</span>
                    <select value={form.salaryCurrency} onChange={(event) => setField('salaryCurrency', event.target.value)}>
                      {['INR', 'USD', 'EUR', 'GBP'].map((currency) => <option key={currency}>{currency}</option>)}
                    </select>
                  </label>
                  <TextField wide label="Work authorization" value={form.workAuthorization} onChange={(value) => setField('workAuthorization', value)} />
                  <div className="profile-switches is-wide">
                    <ToggleTile title="Open to work" detail="Use this profile for recommendations." selected={form.openToWork} onChange={(value) => setField('openToWork', value)} />
                    <ToggleTile title="Willing to relocate" detail="Include roles outside preferred locations." selected={form.willingToRelocate} onChange={(value) => setField('willingToRelocate', value)} />
                  </div>
                </div>
                <SectionActions saving={saving} onCancel={cancel} onSave={commit} />
              </>
            ) : (
              <>
                <Facts items={[
                  { label: 'Expected salary', value: profile.expectedSalary ? `${profile.salaryCurrency} ${profile.expectedSalary}` : '' },
                  { label: 'Work authorization', value: profile.workAuthorization },
                  { label: 'Open to work', value: profile.openToWork ? 'Yes' : 'No' },
                  { label: 'Willing to relocate', value: profile.willingToRelocate ? 'Yes' : 'No' },
                ]} />
                <h3>Target roles</h3>
                <ChipList values={profile.targetRoles} empty="No target roles added." />
                <h3>Preferred locations</h3>
                <ChipList values={profile.preferredLocations} empty="No locations added." />
                <h3>Work preferences</h3>
                <ChipList values={[...profile.workModes, ...profile.employmentTypes]} empty="No work mode or employment type selected." />
              </>
            )}
          </ProfileSection>

          <ProfileSection id="links" title="Online presence" description="Links a recruiter can open." editing={editing === 'links'} onEdit={() => begin('links')}>
            {editing === 'links' ? (
              <>
                <div className="profile-grid">
                  <TextField label="LinkedIn" type="url" value={form.linkedin} onChange={(value) => setField('linkedin', value)} />
                  <TextField label="GitHub" type="url" value={form.github} onChange={(value) => setField('github', value)} />
                  <TextField wide label="Portfolio" type="url" value={form.portfolio} onChange={(value) => setField('portfolio', value)} />
                </div>
                <SectionActions saving={saving} onCancel={cancel} onSave={commit} />
              </>
            ) : (
              <ul className="profile-links">
                {[
                  ['LinkedIn', profile.linkedin],
                  ['GitHub', profile.github],
                  ['Portfolio', profile.portfolio],
                ].map(([label, href]) => (
                  <li key={label}>
                    <span>{label}</span>
                    {href ? <a href={href} target="_blank" rel="noreferrer">{href}</a> : <em>{display('')}</em>}
                  </li>
                ))}
              </ul>
            )}
          </ProfileSection>
        </main>
        <ResumeCard resume={profile.resume} status={status} onUpload={upload} />
      </div>
    </div>
  )
}
