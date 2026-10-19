import { post } from '../../api'
import { Button, Spinner } from '../../components/ui'
import { formatShort } from '../../dates'
import { AiError, AiLabel, useAiEnabled, useAiStatus } from './AiStatus'
import { ObservationsAndSuggestions, type Point } from './Insight'
import { useAiRequest } from './useAiRequest'

interface Result { records_sent: number; observations: Point[]; suggestions: Point[] }

export function ReasonsSummary({ start, end, available }: { start: string; end: string; available: boolean }) {
  const ai = useAiRequest<Result>()
  const { status } = useAiStatus()
  const enabled = useAiEnabled()
  if (!available || !enabled) return null
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line p-3">
      {!ai.data && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" pending={ai.pending} onClick={() => ai.run(() => post<Result>('/ai/reasons-summary', { start, end }))}>
            Summarise reasons with local AI
          </Button>
          <span className="text-xs text-muted">Sends the date, task title, tag and your written reason (first 160 characters) for these records, to the model on this computer.</span>
        </div>
      )}
      {ai.pending && <Spinner label="Thinking locally…" />}
      {ai.error !== null && <AiError error={ai.error} />}
      {ai.data && (
        <>
          <AiLabel model={status?.model} />
          <ObservationsAndSuggestions observations={ai.data.observations} suggestions={ai.data.suggestions}
            renderSupport={(s) => `${formatShort(String(s.date))}: ${s.task_title} (${s.reason})`} />
          <p className="text-xs text-muted">Based on {ai.data.records_sent} records. Counts above this box are calculated by the app, not the AI.</p>
          <div><Button size="sm" variant="ghost" onClick={ai.reset}>Clear</Button></div>
        </>
      )}
    </div>
  )
}
