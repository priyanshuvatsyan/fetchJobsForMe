import { useState } from 'react'
import WorkspacePage from '../../components/WorkspacePage'
import usePreferences from '../../hooks/usePreferences'
import './Settings.css'

const EXPERIENCE = [
  ['all', 'Select', 'All experience levels'],
  ['0', '0 years', 'Freshers, graduates, entry-level roles, and internships'],
  ['1', 'Up to 1 year', 'Roles whose minimum requirement is 0 or 1 year'],
  ['2', 'Up to 2 years', 'Roles whose minimum requirement is 2 years or less'],
  ['3', 'Up to 3 years', 'Roles whose minimum requirement is 3 years or less'],
  ['4', 'Up to 4 years', 'Roles whose minimum requirement is 4 years or less'],
  ['5', 'Up to 5 years', 'Roles whose minimum requirement is 5 years or less'],
]

const POSTED = [
  ['all', 'Select', 'All jobs from the last 15 days'],
  ['today', 'Today', 'Last 24 hours'],
  ['yesterday', 'Yesterday', 'Last 48 hours'],
  ['7days', 'Last 7 days', 'Last seven days'],
  ['15days', 'Last 15 days', 'Last fifteen days'],
]

function optionKey(value) {
  return value == null || value === '' ? 'all' : String(value)
}

function labelFor(options, value) {
  return options.find(([key]) => key === optionKey(value))?.[1] || 'Select'
}

function hintFor(options, value) {
  return options.find(([key]) => key === optionKey(value))?.[2] || ''
}

function maskApiKey(key) {
  if (!key) return 'Not set'
  if (key.length <= 8) return '••••••••'
  return `${key.slice(0, 4)}••••••••${key.slice(-4)}`
}

function SearchPreferences() {
  const { preferences, status, error, save } = usePreferences()
  const [editing, setEditing] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [draft, setDraft] = useState(null)

  const current = draft || {
    ...preferences,
    roles: preferences?.roles || [],
    apiKey: preferences?.apiKey || '',
  }

  const begin = () => {
    setDraft({
      ...preferences,
      roles: [...(preferences?.roles || [])],
      apiKey: preferences?.apiKey || '',
    })
    setEditing(true)
  }

  const cancel = () => {
    setDraft(null)
    setEditing(false)
  }

  const commit = async () => {
    if (await save(draft)) cancel()
  }

  const handleQuickRemove = async () => {
    if (window.confirm('Are you sure you want to remove your stored API key?')) {
      await save({
        ...preferences,
        apiKey: '',
        geminiApiKey: '',
      })
    }
  }

  if (status === 'loading') return <p className="settings-muted">Loading preferences…</p>

  return (
    <div className="search-preferences">
      <div className="search-preferences-head">
        <p>Refresh uses these values when fetching and displaying jobs.</p>
        {!editing ? (
          <button type="button" className="settings-edit" onClick={begin}>
            Edit
          </button>
        ) : null}
      </div>

      {error ? <p className="settings-error">{error.message}</p> : null}

      {editing ? (
        <>
          <div className="settings-form">
            <label className="is-wide">
              <span>Job Provider API Key</span>
              <div className="settings-input-wrap">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={current.apiKey || ''}
                  placeholder="Paste your API key here..."
                  onChange={(event) =>
                    setDraft((value) => ({ ...value, apiKey: event.target.value.trim() }))
                  }
                />
                <div className="settings-input-buttons">
                  {current.apiKey ? (
                    <button
                      type="button"
                      className="settings-action-btn settings-clear-btn"
                      onClick={() => setDraft((value) => ({ ...value, apiKey: '' }))}
                      title="Clear key"
                    >
                      Clear
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="settings-action-btn"
                    onClick={() => setShowKey((prev) => !prev)}
                  >
                    {showKey ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
              <small>Your secret key used for authenticating third-party board fetch queries.</small>
            </label>

            <label>
              <span>Experience</span>
              <select
                value={optionKey(current.experience)}
                onChange={(event) =>
                  setDraft((value) => ({
                    ...value,
                    experience: event.target.value === 'all' ? null : Number(event.target.value),
                  }))
                }
              >
                {EXPERIENCE.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <small>{hintFor(EXPERIENCE, current.experience)}</small>
            </label>

            <label>
              <span>Posted</span>
              <select
                value={optionKey(current.posted)}
                onChange={(event) =>
                  setDraft((value) => ({ ...value, posted: event.target.value }))
                }
              >
                {POSTED.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <small>{hintFor(POSTED, current.posted)}</small>
            </label>

            <label className="is-wide">
              <span>Roles</span>
              <input
                value={current.roles.join(', ')}
                placeholder="Leave blank for every CSE and IT role"
                onChange={(event) => {
                  const roles = event.target.value.split(',').map((role) => role.trimStart())
                  setDraft((value) => ({ ...value, roles }))
                }}
              />
              <small>
                Leave this blank to fetch every CSE and IT role. Abbreviations are included: ML also searches Machine Learning, ML Engineer, and MLOps.
              </small>
            </label>
          </div>

          <div className="settings-actions">
            <button
              type="button"
              className="settings-cancel"
              onClick={cancel}
              disabled={status === 'saving'}
            >
              Cancel
            </button>
            <button
              type="button"
              className="settings-save"
              onClick={commit}
              disabled={status === 'saving'}
            >
              {status === 'saving' ? 'Saving…' : 'Save preferences'}
            </button>
          </div>
        </>
      ) : (
        <dl className="settings-values">
          <div className="is-wide api-key-card">
            <div>
              <dt>API Key</dt>
              <dd className="font-mono">{maskApiKey(preferences?.apiKey)}</dd>
            </div>
            {preferences?.apiKey ? (
              <button
                type="button"
                className="settings-remove-btn"
                onClick={handleQuickRemove}
                disabled={status === 'saving'}
              >
                Remove key
              </button>
            ) : null}
          </div>
          <div>
            <dt>Experience</dt>
            <dd>{labelFor(EXPERIENCE, preferences?.experience)}</dd>
          </div>
          <div>
            <dt>Posted</dt>
            <dd>{labelFor(POSTED, preferences?.posted)}</dd>
          </div>
          <div className="is-wide">
            <dt>Roles</dt>
            <dd>{preferences?.roles?.length ? preferences.roles.join(', ') : 'All CSE and IT roles'}</dd>
          </div>
        </dl>
      )}

      <p className="settings-rule">
        Select on experience keeps every experience level. Select on posted keeps the last 15 days.
        A blank role list keeps every CSE and IT role. These choices are used while fetching from portals.
      </p>
    </div>
  )
}

export default function Settings() {
  return (
    <WorkspacePage
      eyebrow="WORKSPACE PREFERENCES"
      title="Settings"
      description="Manage your API credentials and job-search criteria."
      sections={[
        {
          title: 'Job Search & API Preferences',
          description: 'Configure API key, role keywords, and experience filters.',
          content: <SearchPreferences />,
        },
      ]}
    />
  )
}