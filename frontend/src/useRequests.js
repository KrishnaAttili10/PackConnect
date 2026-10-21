import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './messagingApi'

export function useRequests(refreshKey) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const alive = useRef(false)
  const refresh = useCallback(async () => {
    try {
      const data = await api('/api/requests')
      if (alive.current) {
        setRequests(data.requests)
        setError('')
      }
    } catch (err) {
      if (alive.current) setError(err.message)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    alive.current = true
    const initial = setTimeout(refresh, 0)
    const timer = setInterval(refresh, 8000)
    return () => {
      alive.current = false
      clearInterval(timer)
      clearTimeout(initial)
    }
  }, [refresh, refreshKey])
  return { requests, loading, error, refresh }
}
