import { useEffect, useState } from 'react'
import { ApiError, get } from '../../api'
import { Badge, Button, ErrorNote, Notice } from '../../components/ui'

export interface AiStatus {
  available: boolean
  reason: string | null
  message: string
  provider: string
  model: string
  base_url: string | null
  setup: string[]
  daily_limit: number | null
  used_today: number
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

/** Wording that says where AI requests go: the model on this computer, or Groq's hosted service. */
export function useAiWords() {
  const { status } = useAiStatus()
  const hosted = status?.provider === 'groq'
  return {
    hosted,
    name: hosted ? 'AI' : 'local AI', // "Review habits with AI" / "… with local AI"
    thinking: hosted ? 'Thinking…' : 'Thinking locally…',
    to: hosted ? 'to Groq’s AI service, which doesn’t keep or train on it' : 'to the model on this computer',
  }
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
          <Badge tone={status.available ? 'accent' : 'warn'}>{status.provider === 'groq' ? 'AI' : 'Local AI'} {status.available ? 'ready' : 'unavailable'}</Badge>
        ) : <Badge>Unknown</Badge>}
        {status && <span className="text-muted">Model: {status.model} {status.provider === 'groq' ? 'via Groq' : `via Ollama at ${status.base_url}`}</span>}
        <Button size="sm" variant="ghost" pending={checking} onClick={check}>Check again</Button>
      </div>
      {status && !status.available && <><p>{status.message}</p>{status.reason !== 'disabled' && <SetupSteps status={status} />}</>}
      <p className="text-muted">
        {status?.provider === 'groq'
          ? 'AI runs on Groq’s service, which doesn’t keep or train on what’s sent. '
          : 'AI runs on this computer only. '}
        It is used only when you press an AI button, sees only the records listed before you send, and never
        changes anything until you accept a suggestion. Everything else works without it.
        {status?.daily_limit ? ` You can make ${status.daily_limit} AI requests a day (used today: ${status.used_today}).` : ''}
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
        <p className="mt-1">Everything else in Steady keeps working.{status?.setup.length ? ' To turn on local AI:' : ''}</p>
        {status && status.setup.length > 0 && <SetupSteps status={status} />}
      </div>
    )
  }
  return <ErrorNote message={error instanceof Error ? error.message : 'The AI request failed.'} />
}

export function AiLabel({ model }: { model?: string }) {
  const { name } = useAiWords()
  return (
    <Notice>
      <strong>Suggestion from {name}</strong>{model && ` (${model})`}: review it before using it. Nothing has been changed.
    </Notice>
  )
}
