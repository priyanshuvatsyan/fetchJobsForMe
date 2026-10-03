import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { onAuthStateChanged } from 'firebase/auth'
import Nav from './components/nav/nav'
import { auth } from './firebase'
import Login from './pages/Login/Login'
import Dashboard from './pages/Dashboard/Dashboard'
import JobDiscovery from './pages/JobDiscovery/JobDiscovery'
import RecommendedJobs from './pages/RecommendedJobs/RecommendedJobs'
import Applications from './pages/Applications/Applications'
import ResumeAnalyzer from './pages/ResumeAnalyzer/ResumeAnalyzer'
import EmailResponses from './pages/EmailResponses/EmailResponses'
import SkillsProfile from './pages/SkillsProfile/SkillsProfile'
import AgentActivity from './pages/AgentActivity/AgentActivity'
import Settings from './pages/Settings/Settings'
import './App.css'

import JobsPage from './pages/Jobs/JobsPage'

function RequireAuth() {
  const [user, setUser] = useState(null)
  const [isChecking, setIsChecking] = useState(true)

  useEffect(() => onAuthStateChanged(auth, (currentUser) => {
    setUser(currentUser)
    setIsChecking(false)
  }), [])

  if (isChecking) {
    return <div className="session-check">Restoring your session...</div>
  }

  return user ? <Outlet /> : <Navigate to="/login" replace />
}

function AppLayout({ theme, onToggleTheme }) {
  return (
    <div className="app-shell">
      <Nav theme={theme} onToggleTheme={onToggleTheme} />
      <main className="workspace-main">
        <Outlet />
      </main>
    </div>
  )
}

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('fetchjobs-theme') || 'dark')

  const toggleTheme = () => {
    setTheme((currentTheme) => {
      const nextTheme = currentTheme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('fetchjobs-theme', nextTheme)
      return nextTheme
    })
  }

  return (
    <div className="app-root" data-theme={theme}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AppLayout theme={theme} onToggleTheme={toggleTheme} />}>
            <Route element={<RequireAuth />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="job-discovery" element={<JobDiscovery />} />
              <Route path="recommended-jobs" element={<RecommendedJobs />} />
              <Route path="applications" element={<Applications />} />
              <Route path="resume-analyzer" element={<ResumeAnalyzer />} />
              <Route path="email-responses" element={<EmailResponses />} />
              <Route path="skills-profile" element={<SkillsProfile />} />
              <Route path="agent-activity" element={<AgentActivity />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </div>
  )
}

export default App
