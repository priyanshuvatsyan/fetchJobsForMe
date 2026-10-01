import './WorkspacePage.css'

export default function WorkspacePage({ eyebrow, title, description, metrics, sections, split = false }) {
  return (
    <div className="workspace-page">
      <header className="page-heading">
        <div>
          <p className="page-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p className="page-description">{description}</p>
        </div>
        <div className="page-date">JOBPILOT WORKSPACE</div>
      </header>

      {metrics?.length > 0 && (
        <section className="page-metrics" aria-label={`${title} overview`}>
          {metrics.map((metric) => (
            <div className="page-metric" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              {metric.note && <small>{metric.note}</small>}
            </div>
          ))}
        </section>
      )}

      <div className={`page-sections${split ? ' is-split' : ''}`}>
        {sections.map((section) => (
          <section className={`page-section${section.wide ? ' is-wide' : ''}`} key={section.title}>
            <div className="section-heading">
              <div>
                <h2>{section.title}</h2>
                {section.description && <p>{section.description}</p>}
              </div>
              {section.count && <span>{section.count}</span>}
            </div>
            {section.content ? (
              <div className="section-content">{section.content}</div>
            ) : section.items?.length ? (
              <ul className="section-list">
                {section.items.map((item) => (
                  <li key={item.title}>
                    <span className="list-marker" />
                    <div><strong>{item.title}</strong><p>{item.detail}</p></div>
                    {item.trailing && <small>{item.trailing}</small>}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="section-empty">
                <span className="empty-mark" aria-hidden="true">+</span>
                <p>{section.emptyMessage ?? 'Nothing here yet. Connect a job source or add your first item to get started.'}</p>
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  )
}