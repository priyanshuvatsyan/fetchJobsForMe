import './Callout.css'

/** Inline message block for API errors, portal notes and attribution. */
const Callout = ({ tone = 'info', title = '', children, action = null }) => (
  <div className={`callout callout-${tone}`}>
    <div className="callout-body">
      {title ? <p className="callout-title">{title}</p> : null}
      <div className="callout-content">{children}</div>
    </div>
    {action ? <div className="callout-action">{action}</div> : null}
  </div>
)

export default Callout
