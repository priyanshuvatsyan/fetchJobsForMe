import Login from './pages/Login/Login'
import JobsPage from './pages/Jobs/JobsPage'
import useHashRoute from './hooks/useHashRoute'
import './App.css'

function App() {
  const [route] = useHashRoute()

  if (route === 'jobs') return <JobsPage />

  return <Login />
}

export default App
