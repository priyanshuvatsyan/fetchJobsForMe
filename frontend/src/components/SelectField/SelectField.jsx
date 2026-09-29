import { useId } from 'react'
import './SelectField.css'

const SelectField = ({ label, value, onChange, options, hint = '' }) => {
  const id = useId()

  return (
    <div className="select-field">
      <label className="select-field-label" htmlFor={id}>
        {label}
      </label>
      <div className="select-field-control">
        <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span className="select-field-caret" aria-hidden="true">
          ▾
        </span>
      </div>
      {hint ? <p className="select-field-hint">{hint}</p> : null}
    </div>
  )
}

export default SelectField
