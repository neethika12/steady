import { post } from '../../api'
import { Button, Spinner } from '../../components/ui'
import { AiError, AiLabel, useAiEnabled, useAiStatus, useAiWords } from './AiStatus'
import { ObservationsAndSuggestions, type Point } from './Insight'
import { useAiRequest } from './useAiRequest'

interface Result { records_sent: number; observations: Point[]; suggestions: Point[] }

export function HabitReview({ start, end, available }: { start: string; end: string; available: boolean }) {
  const ai = useAiRequest<Result>()
  const { status } = useAiStatus()
  const enabled = useAiEnabled()
  const words = useAiWords()
  if (!available || !enabled) return null
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line p-3">
      {!ai.data && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" pending={ai.pending} onClick={() => ai.run(() => post<Result>('/ai/habit-review', { start, end }))}>
            Review habits with {words.name}
          </Button>
          <span className="text-xs text-muted">Sends habit names, schedules and the numbers above {words.to}. No journal or task data.</span>
        </div>
      )}
      {ai.pending && <Spinner label={words.thinking} />}
      {ai.error !== null && <AiError error={ai.error} />}
      {ai.data && (
        <>
          <AiLabel model={status?.model} />
          <ObservationsAndSuggestions observations={ai.data.observations} suggestions={ai.data.suggestions}
            renderSupport={(s) => `${s.name}: ${s.completed_days} of ${s.scheduled_days} scheduled days${s.consistency_pct !== null ? ` (${s.consistency_pct}%)` : ''}`} />
          <p className="text-xs text-muted">To act on a suggestion, use the habit’s Edit button. Schedule changes apply from a date you choose, so past days keep their results.</p>
          <div><Button size="sm" variant="ghost" onClick={ai.reset}>Clear</Button></div>
        </>
      )}
    </div>
  )
}
