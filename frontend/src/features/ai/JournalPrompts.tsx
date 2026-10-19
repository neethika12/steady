import { post } from '../../api'
import { Button, Spinner } from '../../components/ui'
import { AiError, useAiEnabled } from './AiStatus'
import { useAiRequest } from './useAiRequest'

/** Prompt ideas. No journal content is sent: the request contains no entry text at all. */
export function JournalPrompts({ onInsert, disabled }: { onInsert: (text: string) => void; disabled?: boolean }) {
  const ai = useAiRequest<{ prompts: string[] }>()
  if (!useAiEnabled()) return null
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" pending={ai.pending} disabled={disabled}
          onClick={() => ai.run(() => post('/ai/journal-prompts', { focus: 'day' }))}>Suggest prompts (local AI)</Button>
        <span className="text-xs text-muted">Nothing you have written is sent.</span>
      </div>
      {ai.pending && <Spinner label="Thinking locally…" />}
      {ai.error !== null && <AiError error={ai.error} />}
      {ai.data && (
        <ul className="flex flex-col gap-1">
          {ai.data.prompts.map((p) => (
            <li key={p} className="flex flex-wrap items-center gap-2">
              <span className="flex-1 italic">{p}</span>
              <Button size="sm" onClick={() => onInsert(p)}>Add to entry</Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
