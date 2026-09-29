import { useEffect, useState } from 'react'
import Button from '../../components/Button/Button'
import Callout from '../../components/Callout/Callout'
import JobFilterBar from '../../components/JobFilterBar/JobFilterBar'
import JobList from '../../components/JobList/JobList'
import Pagination, { PAGE_SIZE } from '../../components/Pagination/Pagination'
import useJobFilters from '../../hooks/useJobFilters'
import useJobs from '../../hooks/useJobs'
import './JobsPage.css'

const DEFAULT_FILTERS = {
  query: '',
  where: '',
  source: 'all',
  boards: '',
  dateRange: 'any',
  sort: 'date_desc',
}

const JobsPage = () => {
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [page, setPage] = useState(1)

  const { jobs, portals, credits, notes, status, error, reload } = useJobs()
  const visibleJobs = useJobFilters(jobs, filters)
  const pageJobs = visibleJobs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  useEffect(() => {
    setPage(1)
  }, [filters])

  const loading = status === 'loading'
  const hiddenByDate = jobs.length - visibleJobs.length

  return (
    <main className="jobs-page">
      <div className="jobs-page-inner">
        <header className="jobs-page-header">
          <div>
            <p className="jobs-page-kicker">fetchJobsForMe</p>
            <h1 className="jobs-page-title">Jobs</h1>
            <p className="jobs-page-subtitle">
              Live openings from public job APIs. Open a card to read the company and role details.
            </p>
          </div>
          <div className="jobs-page-header-actions">
            {jobs.length > 0 ? (
              <span className="jobs-page-count">
                {visibleJobs.length} {visibleJobs.length === 1 ? 'job' : 'jobs'}
                {loading ? ' · still loading' : ''}
              </span>
            ) : null}
            <Button
              variant="secondary"
              className={loading ? 'is-busy' : ''}
              onClick={reload}
              disabled={loading}
            >
              {loading ? 'Loading...' : 'Refresh'}
            </Button>
          </div>
        </header>

        <JobFilterBar
          filters={filters}
          portals={portals}
          onChange={setFilters}
          onReset={() => setFilters(DEFAULT_FILTERS)}
          busy={loading}
        />

        {error ? (
          <Callout
            tone="error"
            title="Could not load jobs"
            action={
              <Button variant="secondary" onClick={reload}>
                Try again
              </Button>
            }
          >
            <p>{error.message}</p>
          </Callout>
        ) : null}

        {notes.length ? (
          <Callout tone="warning" title={`${notes.length} portal ${notes.length === 1 ? 'note' : 'notes'}`}>
            <ul>
              {notes.slice(0, 4).map((note, index) => (
                <li key={index}>
                  <strong>{note.portal}:</strong> {note.message}
                </li>
              ))}
            </ul>
          </Callout>
        ) : null}

        <JobList
          jobs={pageJobs}
          loading={loading && jobs.length === 0}
          emptyTitle={jobs.length ? 'No jobs in this date range' : 'No jobs matched'}
          emptyMessage={
            jobs.length
              ? `${hiddenByDate} ${hiddenByDate === 1 ? 'job is' : 'jobs are'} older than the selected range.`
              : 'Try a different keyword, portal, or company.'
          }
          emptyAction={
            <Button variant="secondary" onClick={() => setFilters(DEFAULT_FILTERS)}>
              Reset filters
            </Button>
          }
        />

        <Pagination
          page={page}
          total={visibleJobs.length}
          onChange={(next) => {
            setPage(next)
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
        />

        {credits.length ? (
          <footer className="jobs-page-credits">
            {credits.map((credit) => (
              <p key={credit}>{credit}</p>
            ))}
          </footer>
        ) : null}
      </div>
    </main>
  )
}

export default JobsPage
