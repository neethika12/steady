import { useState } from 'react'
import { post } from '../../api'
import { Button, Dialog, ErrorNote, Spinner } from '../../components/ui'
import { formatMinutes } from '../../dates'
import { useAction } from '../../hooks'
import type { Task } from '../../types'
import { SplitEditor, stepsPayload, type StepDraft } from '../todo/SplitEditor'
import { AiError, AiLabel, useAiStatus, useAiWords } from './AiStatus'
import { useAiRequest } from './useAiRequest'

interface Proposal {
  steps: { title: string; estimated_minutes: number }[]
  total_minutes: number
  original_estimate: number | null
  exceeds_original_estimate: boolean
  shared: { fields: string[] }
}

export function BreakdownDialog({ task, onClose, onApplied }: {
  task: Task; onClose: () => void; onApplied: () => void
}) {
  const ai = useAiRequest<Proposal>()
  const { status } = useAiStatus()
  const words = useAiWords()
  const [steps, setSteps] = useState<StepDraft[]>([])
  const apply = useAction()

  const ask = () => ai.run(async () => {
    const p = await post<Proposal>('/ai/breakdown', { task_id: task.id })
    setSteps(p.steps.map((s) => ({ title: s.title, estimated_minutes: String(s.estimated_minutes), planned_date: '' })))
    return p
  })

  const accept = async () => {
    const payload = stepsPayload(steps)
    const r = await apply.run(() => post(`/tasks/${task.id}/split`, { steps: payload }))
    if (r) onApplied()
  }

  return (
    <Dialog title="Break into smaller steps" onClose={onClose} wide footer={<>
      <Button onClick={onClose}>{ai.data ? 'Discard' : 'Cancel'}</Button>
      {ai.data
        ? <Button variant="primary" pending={apply.pending} disabled={stepsPayload(steps).length === 0} onClick={accept}>
            Create {stepsPayload(steps).length} task{stepsPayload(steps).length === 1 ? '' : 's'}
          </Button>
        : <Button variant="primary" pending={ai.pending} onClick={ask}>Suggest steps</Button>}
    </>}>
      <div className="flex flex-col gap-4 text-sm">
        <p className="rounded-lg bg-paper p-3"><span className="text-muted">Task:</span> {task.title}</p>
        {!ai.data && !ai.pending && (
          <p className="text-muted">
            Only this task’s title, description and estimate are sent {words.to}
            {status ? ` (${status.model})` : ''}. Nothing is created until you accept.
          </p>
        )}
        {ai.pending && <Spinner label={words.hosted ? 'Thinking…' : 'Thinking locally… this can take 5–20 seconds.'} />}
        {ai.error !== null && <AiError error={ai.error} />}
        {ai.data && (
          <>
            <AiLabel model={status?.model} />
            <p>
              Total: {formatMinutes(ai.data.total_minutes)}
              {ai.data.original_estimate && <> (your estimate was {formatMinutes(ai.data.original_estimate)}{ai.data.exceeds_original_estimate && ': these steps add up to more'})</>}.
              Edit, remove or add steps, then accept. The original task is marked as split; its history is kept.
            </p>
            <SplitEditor steps={steps} onChange={setSteps} />
          </>
        )}
        {apply.error && <ErrorNote message={apply.error} />}
      </div>
    </Dialog>
  )
}
