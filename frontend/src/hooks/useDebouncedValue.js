import { useEffect, useState } from 'react'

/** Delay a fast-changing value so typing does not trigger a request per keystroke. */
export function useDebouncedValue(value, delay = 500) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

export default useDebouncedValue
