import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Callout from '../../components/Callout/Callout'
import JobList from '../../components/JobList/JobList'
import WorkspacePage from '../../components/WorkspacePage'
import { fetchSummary } from '../../api/saved'
import useSavedJobs from '../../hooks/useSavedJobs'
import { formatPostedAt } from '../../utils/jobs'
import '../../styles/jobTheme.css'
import './JobDiscovery.css'

const EMPTY_SUMMARY = { sourcesConnected: 0, sources: [], total: 0, newToday: 0, fetchedAt: '' }

function useSummary() {
  const [summary, setSummary] = useState(EMPTY_SUMMARY)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchSummary(controller.signal)
      .then(setSummary)
      .catch((cause) => {
        if (cause.name !== 'AbortError') setError(cause)
      })
    return () => controller.abort()
  }, [])

  return { summary, error }
}

export default function JobDiscovery() {
  const { summary, error: summaryError } = useSummary()
  const { saved, savedLinks, toggle, status, error: saveError } = useSavedJobs()
  const lastFetch = formatPostedAt(summary.fetchedAt)

  const savedContent = (
    <div className="job-theme discovery-saved">
      {saveError ? (
        <Callout tone="error" title="Could not update saved jobs">
          <p>{saveError.message}</p>
        </Callout>
      ) : null}
      <JobList
        jobs={saved}
        loading={status === 'loading'}
        skeletonCount={2}
        savedLinks={savedLinks}
        onToggleSave={toggle}
        emptyTitle="No saved jobs yet"
        emptyMessage="Tap the star on a job to keep it here."
        emptyAction={<Link className="discovery-browse" to="/jobs">Browse jobs</Link>}
      />
    </div>
  )

  return (
    <>
      {summaryError ? (
        <div className="job-theme discovery-error">
          <Callout tone="error" title="Could not load job stats">
            <p>{summaryError.message}</p>
          </Callout>
        </div>
      ) : null}
      <WorkspacePage
        split
        eyebrow="FIND YOUR NEXT ROLE"
        title="Job Discovery"
        description="Search roles across your connected job sources and keep promising opportunities close."
        metrics={[
          { label: 'Sources connected', value: String(summary.sourcesConnected), note: `${summary.total} jobs` },
          { label: 'New today', value: String(summary.newToday), note: 'Posted in the last 24 hours' },
          { label: 'Saved jobs', value: String(saved.length) },
          { label: 'Last search', value: lastFetch || 'Not run' },
        ]}
        sections={[
          {
            title: 'Saved jobs',
            description: 'Jobs you starred. They stay here until you remove the star.',
            count: saved.length ? String(saved.length) : '',
            content: savedContent,
          },
          {
            title: 'Connected sources',
            description: 'Portals that returned jobs in the latest fetch.',
            items: summary.sources.map((source) => ({
              title: source.label,
              detail: source.status === 'paused' ? 'Paused · showing saved results' : `Status: ${source.status}`,
              trailing: `${source.count} jobs`,
            })),
            emptyMessage: 'No portal has returned jobs yet. Open Jobs and press Refresh.',
          },
        ]}
      />
    </>
  )
}
