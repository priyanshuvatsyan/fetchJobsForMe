import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import { signOut } from 'firebase/auth'
import { auth } from '../../firebase'
import './nav.css'

const navigationItems = [
  { label: 'Dashboard', path: '/dashboard', icon: 'dashboard' },
  { label: 'Job Discovery', path: '/job-discovery', icon: 'search' },
  { label: 'Recommended Jobs', path: '/recommended-jobs', icon: 'sparkles' },
  { label: 'Applications', path: '/applications', icon: 'applications' },
  { label: 'Resume Analyzer', path: '/resume-analyzer', icon: 'resume' },
  { label: 'Email & Responses', path: '/email-responses', icon: 'email', badge: '3' },
  { label: 'Skills & Profile', path: '/skills-profile', icon: 'profile' },
  { label: 'Agent Activity', path: '/agent-activity', icon: 'activity' },
  { label: 'Settings', path: '/settings', icon: 'settings' },
]

function NavIcon({ name }) {
  const shared = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  }

  const icons = {
    dashboard: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
    sparkles: <><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></>,
    applications: <><rect x="5" y="4" width="14" height="16" rx="2" /><path d="M9 4V2h6v2M9 9h6M9 13h6M9 17h3" /></>,
    resume: <><path d="M6 3h8l5 5v5M14 3v6h5M6 3v18h7" /><circle cx="17" cy="17" r="3" /><path d="m19.2 19.2 2 2" /></>,
    email: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></>,
    profile: <><path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6l8-3Z" /><circle cx="12" cy="10" r="2.2" /><path d="M8.5 16c.8-1.6 2-2.4 3.5-2.4s2.7.8 3.5 2.4" /></>,
    activity: <><path d="M3 12h4l2.2-7 4.1 14 2.2-7H21" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.1.9-1.4 2.4-1.4-.5a7.7 7.7 0 0 1-1.5.9l-.2 1.5h-2.8l-.3-1.5a7.7 7.7 0 0 1-1.5-.9l-1.4.5-1.4-2.4 1.1-.9a7.8 7.8 0 0 1 0-1.8l-1.1-.9 1.4-2.4 1.4.5a7.7 7.7 0 0 1 1.5-.9l.3-1.5h2.8l.2 1.5a7.7 7.7 0 0 1 1.5.9l1.4-.5 1.4 2.4-1.1.9a7.8 7.8 0 0 1-.1 1.7Z" transform="translate(-1 -1)" /></>,
  }

  return <svg {...shared}>{icons[name]}</svg>
}

export default function Nav() {
  const navigate = useNavigate()
  const [logoutError, setLogoutError] = useState('')

  const handleLogout = async () => {
    setLogoutError('')
    try {
      await signOut(auth)
      navigate('/login', { replace: true })
    } catch {
      setLogoutError('Could not log out. Please try again.')
    }
  }

  return (
    <aside className="side-nav">
      <NavLink to="/dashboard" className="brand-lockup" aria-label="JobPilot AI dashboard">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 9h14v11H5zM8 9V6a4 4 0 0 1 8 0v3M9 14h.01M15 14h.01M10 17h4" />
          </svg>
        </span>
        <span className="brand-copy">
          <strong>Fetch Jobs For Me</strong>
          <small>PERSONAL AGENT</small>
        </span>
      </NavLink>

      <nav className="nav-links" aria-label="Main navigation">
        {navigationItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/dashboard'}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            <NavIcon name={item.icon} />
            <span>{item.label}</span>
            {item.badge && <span className="nav-badge">{item.badge}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="nav-footer">
        <div className="agent-status">
          <strong><span className="online-dot" />Agent Online</strong>
          <p>Monitoring 6 portals · next search in 24 min</p>
        </div>
        <div className="application-usage">
          <div><span>Applications this month</span><strong>18 / 30</strong></div>
          <div className="usage-track"><span /></div>
        </div>
        {logoutError && <p className="logout-error" role="alert">{logoutError}</p>}
        <button className="logout-button" type="button" onClick={handleLogout}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10 17l5-5-5-5M15 12H3M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" />
          </svg>
          <span>Log out</span>
        </button>
      </div>
    </aside>
  )
}