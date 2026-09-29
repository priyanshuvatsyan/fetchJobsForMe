import './EmptyState.css'

const EmptyState = ({ icon = '🗂️', title = 'Nothing here', message = '', action = null }) => (
  <div className="empty-state">
    <span className="empty-state-icon" aria-hidden="true">
      {icon}
    </span>
    <h3 className="empty-state-title">{title}</h3>
    {message ? <p className="empty-state-message">{message}</p> : null}
    {action ? <div className="empty-state-action">{action}</div> : null}
  </div>
)

export default EmptyState
