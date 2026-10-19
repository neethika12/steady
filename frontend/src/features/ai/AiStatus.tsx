import { useEffect, useState } from 'react'
import { ApiError, get } from '../../api'
import { Badge, Button, ErrorNote, Notice } from '../../components/ui'

export interface AiStatus {
  available: boolean
  reason: string | null
  message: string
  provider: string
  model: string
  base_url: string
  setup: string[]
}

let cached: AiStatus | null = null

export function useAiStatus() {
  const [status, setStatus] = useState<AiStatus | null>(cached)
  const [checking, setChecking] = useState(false)
  const check = async () => {
    setChecking(true)
    try { cached = await get<AiStatus>('/ai/status'); setStatus(cached) } catch { /* shown as unknown */ } finally { setChecking(false) }
  }
  useEffect(() => { if (!cached) void check() }, [])
  return { status, checking, check }
}

/** False on servers where AI is turned off (AI_ENABLED=false): AI buttons are hidden there. */
export function useAiEnabled(): boolean {
  const { status } = useAiStatus()
  return status?.reason !== 'disabled'
}

export function SetupSteps({ status }: { status: AiStatus }) {
  return (
    <ol className="mt-2 list-inside list-decimal space-y-1 text-sm">
      {status.setup.map((s) => <li key={s}><code className="text-xs">{s}</code></li>)}
    </ol>
  )
}

export function AiStatusPanel() {
  const { status, checking, check } = useAiStatus()
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {status ? (
          <Badge tone={status.available ? 'accent' : 'warn'}>{status.available ? 'Local AI ready' : 'Local AI unavailable'}</Badge>
        ) : <Badge>Unknown</Badge>}
        {status && <span className="text-muted">Model: {status.model} via Ollama at {status.base_url}</span>}
        <Button size="sm" variant="ghost" pending={checking} onClick={check}>Check again</Button>
      </div>
      {status && !status.available && <><p>{status.message}</p>{status.reason !== 'disabled' && <SetupSteps status={status} />}</>}
      <p className="text-muted">
        AI runs on this computer only. It is used only when you press an AI button, sees only the records listed
        before you send, and never changes anything until you accept a suggestion. Everything else works without it.
      </p>
    </div>
  )
}

/** Error display that turns "unavailable" into setup guidance instead of a raw error. */
export function AiError({ error }: { error: unknown }) {
  const { status } = useAiStatus()
  if (error instanceof ApiError && error.code === 'ai_unavailable') {
    return (
      <div role="alert" className="rounded-lg border border-warn/40 bg-warn-soft p-3 text-sm text-warn">
        <p className="font-medium">{error.message}</p>
        <p className="mt-1">Everything else in Steady keeps working. To turn on local AI:</p>
        {status && <SetupSteps status={status} />}
      </div>
    )
  }
  return <ErrorNote message={error instanceof Error ? error.message : 'The AI request failed.'} />
}

export function AiLabel({ model }: { model?: string }) {
  return (
    <Notice>
      <strong>Suggestion from local AI</strong>{model && ` (${model})`}: review it before using it. Nothing has been changed.
    </Notice>
  )
}
