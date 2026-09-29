import { useEffect, useState } from 'react'

function currentRoute() {
  return window.location.hash.replace(/^#\/?/, '') || ''
}

/** Small hash router so the jobs page is its own route without extra packages. */
export function useHashRoute() {
  const [route, setRoute] = useState(currentRoute)

  useEffect(() => {
    const onChange = () => setRoute(currentRoute())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = (next) => {
    window.location.hash = next ? `#/${next}` : '#/'
  }

  return [route, navigate]
}

export default useHashRoute
