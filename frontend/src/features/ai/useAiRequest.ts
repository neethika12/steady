import { useCallback, useRef, useState } from 'react'

/** One AI request at a time, with the raw error kept so AiError can show setup help. */
export function useAiRequest<T>() {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)
  const busy = useRef(false)
  const run = useCallback(async (fn: () => Promise<T>) => {
    if (busy.current) return
    busy.current = true
    setPending(true)
    setError(null)
    try { setData(await fn()) } catch (err) { setError(err) } finally { busy.current = false; setPending(false) }
  }, [])
  return { data, error, pending, run, reset: () => { setData(null); setError(null) } }
}
