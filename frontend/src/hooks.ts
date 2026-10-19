import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from './api'

export interface Loaded<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
  setData: (value: T) => void
}

/** Load data whenever `key` changes. Keeps showing old data while reloading. */
export function useLoad<T>(loader: (signal: AbortSignal) => Promise<T>, key: string): Loaded<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    loaderRef.current(controller.signal)
      .then((value) => { if (!controller.signal.aborted) setData(value) })
      .catch((err) => { if (!controller.signal.aborted) setError(errorMessage(err)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [key, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, reload, setData }
}

/** Run an async action once at a time; exposes pending state and the last error. */
export function useAction() {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busy = useRef(false)

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (busy.current) return undefined // ignore double clicks while a request is running
    busy.current = true
    setPending(true)
    setError(null)
    try {
      return await fn()
    } catch (err) {
      setError(errorMessage(err))
      return undefined
    } finally {
      busy.current = false
      setPending(false)
    }
  }, [])

  return { run, pending, error, setError }
}

// ---- tiny change notifications between tabs/panels ----

export type Topic = 'tasks' | 'habits' | 'journal' | 'money'

export function notifyChanged(...topics: Topic[]) {
  window.dispatchEvent(new CustomEvent('steady:changed', { detail: topics }))
}

/** Call `reload` whenever another part of the app changes one of `topics`. */
export function useOnChanged(topics: Topic[], reload: () => void) {
  const key = topics.join(',')
  useEffect(() => {
    const handler = (e: Event) => {
      const changed = (e as CustomEvent<Topic[]>).detail
      if (changed.some((t) => key.split(',').includes(t))) reload()
    }
    window.addEventListener('steady:changed', handler)
    return () => window.removeEventListener('steady:changed', handler)
  }, [key, reload])
}
