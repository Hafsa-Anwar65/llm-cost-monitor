import { useCallback, useEffect, useState } from 'react'
import type { Dashboard, Query } from './types'

export function toSearch(q: Query): string {
  const p = new URLSearchParams()
  p.set('range', q.range)
  p.set('tz', Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  q.providers.forEach((v) => p.append('provider', v))
  q.models.forEach((v) => p.append('model', v))
  q.users.forEach((v) => p.append('user', v))
  q.features.forEach((v) => p.append('feature', v))
  return p.toString()
}

/** Fetches the dashboard. The previous data stays on screen while a refetch is in flight. */
export function useDashboard(query: Query, live: boolean) {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const search = toSearch(query)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetch(`/api/dashboard?${search}`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`The API answered with status ${res.status}.`)
        return (await res.json()) as Dashboard
      })
      .then((next) => {
        setData(next)
        setError(null)
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return
        setError(err instanceof TypeError ? "Can't reach the proxy API." : err.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [search, tick])

  useEffect(() => {
    if (!live) return
    const id = window.setInterval(() => setTick((t) => t + 1), 5000)
    return () => window.clearInterval(id)
  }, [live])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, reload }
}

type Theme = 'light' | 'dark'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
  })

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.dataset.theme = next
    try {
      localStorage.setItem('lcm-theme', next)
    } catch {
      /* storage can be blocked; the toggle still works for this visit */
    }
  }, [theme])

  return { theme, toggle }
}

export function usePrefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Which section is nearest the top of the viewport, for the active pill in the nav. */
export function useActiveSection(ids: string[], ready: boolean): string {
  const [active, setActive] = useState(ids[0])
  const key = ids.join(',')
  useEffect(() => {
    if (!ready) return
    const onScroll = () => {
      const line = window.innerHeight * 0.35
      let current = ids[0]
      for (const id of ids) {
        const el = document.getElementById(id)
        if (el && el.getBoundingClientRect().top <= line) current = id
      }
      setActive(current)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready])
  return active
}
