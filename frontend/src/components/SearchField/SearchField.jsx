import { useId } from 'react'
import './SearchField.css'

const SearchField = ({ label, value, onChange, placeholder = '', icon = '🔍', hint = '' }) => {
  const id = useId()

  return (
    <div className="search-field">
      <label className="search-field-label" htmlFor={id}>
        {label}
      </label>
      <div className="search-field-input">
        <span className="search-field-icon" aria-hidden="true">
          {icon}
        </span>
        <input
          id={id}
          type="search"
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {hint ? <p className="search-field-hint">{hint}</p> : null}
    </div>
  )
}

export default SearchField
