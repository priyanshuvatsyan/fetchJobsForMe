import JobCard from '../JobCard/JobCard'
import JobCardSkeleton from '../JobCard/JobCardSkeleton'
import EmptyState from '../EmptyState/EmptyState'
import './JobList.css'

const JobList = ({ jobs, loading, skeletonCount = 4, emptyTitle, emptyMessage, emptyAction }) => {
  if (loading) {
    return (
      <div className="job-list" aria-busy="true">
        {Array.from({ length: skeletonCount }, (_, index) => (
          <JobCardSkeleton key={index} />
        ))}
      </div>
    )
  }

  if (!jobs.length) {
    return <EmptyState title={emptyTitle} message={emptyMessage} action={emptyAction} />
  }

  return (
    <div className="job-list">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
  )
}

export default JobList
