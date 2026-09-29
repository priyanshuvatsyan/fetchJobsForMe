import './JobCardSkeleton.css'

const JobCardSkeleton = () => (
  <div className="job-card-skeleton" aria-hidden="true">
    <div className="skeleton-avatar" />
    <div className="skeleton-lines">
      <div className="skeleton-line skeleton-line-title" />
      <div className="skeleton-line skeleton-line-company" />
      <div className="skeleton-line skeleton-line-meta" />
    </div>
  </div>
)

export default JobCardSkeleton
