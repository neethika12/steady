import { useMemo, useState } from 'react'
import { get, post } from '../../api'
import { Badge, Button, Dialog, ErrorNote, Field, Loading, Spinner, fieldBase, useToast } from '../../components/ui'
import { formatLong, formatMinutes, formatShort } from '../../dates'
import { notifyChanged, useAction, useLoad } from '../../hooks'
import type { Day, Task } from '../../types'
import { PRIORITY_LABEL } from '../todo/labels'
import { AiError, AiLabel, useAiStatus } from './AiStatus'
import { useAiRequest } from './useAiRequest'

interface Row { ref: string; task_id: string; title: string; estimated_minutes: number | null; reason: string; priority: string; deadline: string | null; why?: string }
interface Proposal {
  plan: Row[]; left_out: Row[]; not_selected: { task_id: string; title: string }[]
  planned_minutes: number; unestimated_count: number; model_respected_budget: boolean; note: string
}

export function DailyPlanDialog({ date, onClose }: { date: string; onClose: () => void }) {
  const day = useLoad<Day>((s) => get(`/plans/day?date=${date}`, s), `dp-day-${date}`)
  const backlog = useLoad<Task[]>((s) => get('/tasks?view=inbox', s), 'dp-backlog')
  const candidates = useMemo(() => {
    const planned = (day.data?.plans ?? []).filter((p) => p.state === 'planned' || p.state === 'awaiting_review').map((p) => p.task)
    return [...planned, ...(backlog.data ?? [])].filter((t) => t.status === 'active').slice(0, 25)
  }, [day.data, backlog.data])
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const selected = picked ?? new Set(candidates.map((t) => t.id))
  const [minutes, setMinutes] = useState(240)
  const ai = useAiRequest<Proposal>()
  const { status } = useAiStatus()
  const [accept, setAccept] = useState<Set<string>>(new Set())
  const apply = useAction()
  const toast = useToast()

  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id); else next.add(id)
    setPicked(next)
  }
  const ask = () => ai.run(async () => {
    const p = await post<Proposal>('/ai/daily-plan', { date, available_minutes: minutes, task_ids: [...selected] })
    setAccept(new Set(p.plan.map((r) => r.task_id)))
    return p
  })
  const confirm = async () => {
    if (await apply.run(() => post('/plans/batch', { date, task_ids: [...accept] }))) {
      toast(`Planned ${accept.size} task${accept.size === 1 ? '' : 's'} for ${formatShort(date)}`)
      notifyChanged('tasks'); onClose()
    }
  }

  return (
    <Dialog title={`Suggest a plan · ${formatLong(date)}`} onClose={onClose} wide footer={<>
      <Button onClick={onClose}>{ai.data ? 'Discard' : 'Cancel'}</Button>
      {ai.data
        ? <Button variant="primary" pending={apply.pending} disabled={accept.size === 0} onClick={confirm}>Plan {accept.size} task{accept.size === 1 ? '' : 's'} for this day</Button>
        : <Button variant="primary" pending={ai.pending} disabled={selected.size === 0} onClick={ask}>Suggest a plan</Button>}
    </>}>
      <div className="flex flex-col gap-4 text-sm">
        {!ai.data && (
          <>
            <Field label="Time available for tasks (minutes)" htmlFor="dp-min" hint="The app, not the AI, checks that the plan fits this time.">
              <input id="dp-min" type="number" min={15} max={960} step={15} className={`${fieldBase} w-32`} value={minutes}
                onChange={(e) => setMinutes(Math.min(960, Math.max(15, Number(e.target.value) || 15)))} />
            </Field>
            <fieldset>
              <legend className="mb-1 font-medium">Tasks to consider ({selected.size} selected)</legend>
              <div className="mb-1 flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(candidates.map((t) => t.id)))}>Select all</Button>
                <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Select none</Button>
              </div>
              <p className="mb-2 text-muted">Sent for each: title, priority, deadline and estimate. Descriptions are not sent.</p>
              {(day.loading || backlog.loading) && !candidates.length && <Loading />}
              {!day.loading && !backlog.loading && candidates.length === 0 && <p className="text-muted">No active tasks for this day or unscheduled. Add some tasks first.</p>}
              <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto">
                {candidates.map((t) => (
                  <li key={t.id}>
                    <label className="flex items-center gap-2 rounded px-1 py-1 hover:bg-paper">
                      <input type="checkbox" className="size-4 accent-accent" checked={selected.has(t.id)} onChange={() => toggle(t.id)} />
                      <span className="flex-1">{t.title}</span>
                      <span className="text-xs text-muted">{PRIORITY_LABEL[t.priority]} · {formatMinutes(t.estimated_minutes)}{t.deadline && ` · due ${formatShort(t.deadline)}`}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          </>
        )}
        {ai.pending && <Spinner label="Thinking locally… this can take 5–20 seconds." />}
        {ai.error !== null && <AiError error={ai.error} />}
        {ai.data && (
          <>
            <AiLabel model={status?.model} />
            <div className="flex flex-wrap gap-2">
              <Badge tone="accent">{formatMinutes(ai.data.planned_minutes)} of {formatMinutes(minutes)} planned</Badge>
              {ai.data.model_respected_budget
                ? <Badge>Fits the available time</Badge>
                : <Badge tone="warn">The AI chose too much; the app removed tasks that didn’t fit</Badge>}
              {ai.data.unestimated_count > 0 && <Badge tone="warn">{ai.data.unestimated_count} without an estimate (not counted in the time)</Badge>}
            </div>
            <section>
              <h3 className="mb-1 font-semibold">Suggested order</h3>
              <ol className="flex flex-col gap-1.5">
                {ai.data.plan.map((r, i) => (
                  <li key={r.task_id}>
                    <label className="flex items-start gap-2 rounded-lg border border-line p-2">
                      <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={accept.has(r.task_id)}
                        onChange={() => { const n = new Set(accept); if (n.has(r.task_id)) n.delete(r.task_id); else n.add(r.task_id); setAccept(n) }} />
                      <span className="flex-1"><strong>{i + 1}. {r.title}</strong> <span className="text-muted">· {formatMinutes(r.estimated_minutes)}</span>
                        <span className="block text-muted">Why: {r.reason}</span></span>
                    </label>
                  </li>
                ))}
              </ol>
            </section>
            {ai.data.left_out.length > 0 && (
              <section><h3 className="mb-1 font-semibold">Removed by the app to fit your time</h3>
                <ul className="list-inside list-disc text-muted">{ai.data.left_out.map((r) => <li key={r.task_id}>{r.title}: {r.why}</li>)}</ul></section>
            )}
            {ai.data.not_selected.length > 0 && (
              <p className="text-muted">Not chosen: {ai.data.not_selected.map((r) => r.title).join(', ')}</p>
            )}
            {ai.data.note && <p className="text-muted">Note from the AI: {ai.data.note}</p>}
            <Button size="sm" variant="ghost" onClick={ai.reset}>← Change inputs</Button>
          </>
        )}
        {apply.error && <ErrorNote message={apply.error} />}
      </div>
    </Dialog>
  )
}
