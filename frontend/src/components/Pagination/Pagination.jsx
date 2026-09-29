import './Pagination.css'

const PAGE_SIZE = 20

function pageCount(total) {
  return Math.max(1, Math.ceil(total / PAGE_SIZE))
}

/** Page buttons with the current page kept in the middle of a short window. */
function visiblePages(current, total) {
  const start = Math.max(1, Math.min(current - 2, total - 4))
  const end = Math.min(total, start + 4)
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
}

const Pagination = ({ page, total, onChange }) => {
  if (total <= PAGE_SIZE) return null
  const pages = pageCount(total)
  const from = (page - 1) * PAGE_SIZE + 1
  const to = Math.min(total, page * PAGE_SIZE)

  return (
    <nav className="pagination" aria-label="Job pages">
      <p className="pagination-status">
        {from}–{to} of {total}
      </p>
      <div className="pagination-controls">
        <button type="button" onClick={() => onChange(page - 1)} disabled={page <= 1}>
          Previous
        </button>
        {visiblePages(page, pages).map((number) => (
          <button
            key={number}
            type="button"
            className={number === page ? 'is-current' : ''}
            aria-current={number === page ? 'page' : undefined}
            onClick={() => onChange(number)}
          >
            {number}
          </button>
        ))}
        <button type="button" onClick={() => onChange(page + 1)} disabled={page >= pages}>
          Next
        </button>
      </div>
    </nav>
  )
}

export { PAGE_SIZE }
export default Pagination
