import Button from '../Button/Button'
import SearchField from '../SearchField/SearchField'
import { SegmentedControl } from '../JobCard/JobCard'
import SelectField from '../SelectField/SelectField'
import { DATE_RANGES, SORT_OPTIONS } from '../../utils/jobs'
import './JobFilterBar.css'

const DATE_OPTIONS = Object.entries(DATE_RANGES).map(([value, range]) => ({
  value,
  label: range.label,
}))

/**
 * Filters apply to the jobs already loaded. The portal value is the API key
 * (for example fourdayweek), matched to each job's portalKey.
 */
const JobFilterBar = ({ filters, portals, onChange, onReset, busy }) => {
  const set = (key) => (value) => onChange({ ...filters, [key]: value })

  const portalOptions = [
    { value: 'all', label: 'All portals' },
    ...portals.map((portal) => ({ value: portal.key, label: portal.label })),
  ]

  return (
    <section className="job-filter-bar" aria-label="Job filters">
      <div className="job-filter-row">
        <SearchField
          label="Search"
          value={filters.query}
          onChange={set('query')}
          placeholder="Role, company or keyword"
        />
        <SearchField
          label="Location"
          value={filters.where}
          onChange={set('where')}
          placeholder="Bengaluru, Hyderabad, Remote"
          icon="📍"
        />
        <SelectField
          label="Portal"
          value={filters.source}
          onChange={set('source')}
          options={portalOptions}
        />
      </div>

      <div className="job-filter-row job-filter-row-secondary">
        <SegmentedControl
          label="Posted"
          value={filters.dateRange}
          onChange={set('dateRange')}
          options={DATE_OPTIONS}
        />
        <SelectField label="Sort by" value={filters.sort} onChange={set('sort')} options={SORT_OPTIONS} />
        <SearchField
          label="Companies"
          value={filters.boards}
          onChange={set('boards')}
          placeholder="discord, stripe (Greenhouse, Lever, Ashby)"
          icon="🏢"
        />
        <div className="job-filter-reset">
          <Button variant="secondary" onClick={onReset} disabled={busy}>
            Reset
          </Button>
        </div>
      </div>
    </section>
  )
}

export default JobFilterBar
