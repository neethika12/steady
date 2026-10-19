import { useState } from 'react'
import { post, put } from '../../api'
import { MoveToDateDialog } from '../../components/MoveToDateDialog'
import { Badge, Button, ErrorNote, cx, inputClass, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { addDays, formatClock, formatShort, formatTimeRange } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import type { Plan, Reason } from '../../types'
import { BreakdownDialog } from '../ai/BreakdownDialog'
import { useAiEnabled } from '../ai/AiStatus'
import { notDoneMessage } from '../../components/Motivation'
import { DeleteTaskDialog } from './DeleteTaskDialog'
import { rangeMinutes, setTaskDragData } from './dropToDay'
import { CANCEL_EXPLANATION, REASONS, REASON_LABEL } from './labels'
import { TaskBadges } from './TaskBadges'
import { TaskFormDialog } from './TaskForm'
import { TaskHistoryDialog } from './TaskHistory'

export { TASK_DRAG_TYPE } from './dropToDay'

/**
 * One task on one day. What you can do depends only on that day's state:
 *   open (planned / awaiting review) → Completed · Not completed · ⋯
 *   completed / not completed       → Undo · ⋯ (edit, history)
 *   cancelled                        → Restore · History
 */
export function PlanRow({ plan, onChanged, compact = false, hideTime = false, startAskingReason = false, expanded = false }: {
  plan: Plan; onChanged: () => void; compact?: boolean; hideTime?: boolean; startAskingReason?: boolean
  expanded?: boolean // show all actions straight away (used in the task panel)
}) {
  const aiEnabled = useAiEnabled()
  const { today, settings } = useApp()
  const [more, setMore] = useState(expanded)
  const [askReason, setAskReason] = useState(startAskingReason && (plan.state === 'planned' || plan.state === 'awaiting_review'))
  const [dialog, setDialog] = useState<'move' | 'edit' | 'history' | 'breakdown' | 'delete' | null>(null)
  const action = useAction()
  const toast = useToast()
  const task = plan.task
  const open = plan.state === 'planned' || plan.state === 'awaiting_review'
  const unfinished = plan.state === 'not_completed' || plan.state === 'partial'
  const started = plan.plan_date <= today
  const movable = open && task.status === 'active'
  // After "Not completed": Inbox tasks go back to the Inbox; tasks created on a day stay here
  // until you choose (move to tomorrow, move to the Inbox, or leave it).
  const undecided = unfinished && task.status === 'active' && !task.planned_date && !plan.carried_to_date && !plan.follow_up
  const fromInbox = task.origin === 'inbox' 
  const nextDay = plan.plan_date < today ? today : addDays(today, 1)

  const changed = (msg?: string) => { if (msg) toast(msg); notifyChanged('tasks'); onChanged() }
  const call = async (fn: () => Promise<unknown>, msg?: string) => { if (await action.run(fn) !== undefined) changed(msg) }
  const review = (outcome: 'completed' | null, msg?: string, note?: string) =>
    call(() => put(`/plans/${plan.id}/review`, { outcome, correction_note: note ?? null }), msg)

  return (
    <li
      draggable={movable}
      onDragStart={(e) => setTaskDragData(e, task.id, rangeMinutes(plan.planned_time, plan.planned_end_time) ?? task.estimated_minutes)}
      className={cx('rounded-lg border bg-card px-3 py-2', movable && 'cursor-grab',
        plan.state === 'completed' ? 'border-accent/30' : 'border-line')}
    >
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        {!hideTime && (
          <span className={cx('shrink-0 rounded-md px-1.5 py-0.5 text-xs font-medium',
            plan.planned_time ? 'bg-accent-soft text-accent' : 'bg-ink/5 text-muted', compact && 'mt-0.5')}>
            {formatTimeRange(plan.planned_time, plan.planned_end_time)}
          </span>
        )}
        <div className="min-w-[9rem] flex-1">
          <span className={cx('break-words text-sm font-medium',
            (plan.state === 'completed' || plan.state === 'cancelled') && 'text-muted line-through')}>{task.title}</span>
          {!compact && <div className="mt-1"><TaskBadges task={task} plan={plan} today={today} /></div>}
          {compact && plan.state !== 'planned' && <span className="block text-xs text-muted">{stateText(plan)}</span>}
        </div>

        {!compact && (
          <div className="flex flex-wrap items-center gap-1.5">
            {open && started && !askReason && <>
              <Button size="sm" variant="primary" pending={action.pending} onClick={() => review('completed')}
                aria-label={`Mark completed: ${task.title}`}>✓ Completed</Button>
              <Button size="sm" onClick={() => setAskReason(true)} aria-label={`Mark not completed: ${task.title}`}>✗ Not completed</Button>
            </>}
            {open && !started && <span className="text-xs text-muted">Upcoming</span>}
            {plan.state === 'completed' && <>
              <Badge tone="accent">✓ Completed{plan.completed_at && ` · ${formatClock(plan.completed_at, settings.timezone)}`}</Badge>
              <Button size="xs" variant="ghost" pending={action.pending} onClick={() => review(null, 'Undone', 'Undone in the day view')}>Undo</Button>
            </>}
            {unfinished && <>
              <Badge tone="danger">✗ Not completed</Badge>
              <Button size="xs" variant="ghost" pending={action.pending} onClick={() => review(null, 'Undone', 'Undone in the day view')}>Undo</Button>
            </>}
            {plan.state === 'cancelled' && <>
              <Badge title={CANCEL_EXPLANATION}>Cancelled · not counted</Badge>
              {(task.status === 'cancelled' || task.archived_at) && (
                <Button size="xs" variant="ghost" pending={action.pending} title="Undo the cancellation: the task goes back to this day"
                  onClick={() => call(() => post(`/tasks/${task.id}/restore`), `Restored to ${formatShort(plan.plan_date)}`)}>Restore</Button>
              )}
            </>}
          </div>
        )}
        <Button size="sm" variant="ghost" aria-expanded={more} aria-label={`More actions for ${task.title}`} onClick={() => setMore(!more)}>⋯</Button>
      </div>

      {unfinished && !compact && (
        <div className="mt-2 rounded-md bg-paper px-3 py-2 text-sm">
          <span className="text-muted">Why: </span>{plan.reason_note || (plan.reason ? REASON_LABEL[plan.reason] : 'No reason recorded')}
          {plan.reason && plan.reason_note && <span className="ml-1"><Badge>{REASON_LABEL[plan.reason]}</Badge></span>}
          {undecided && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span className={fromInbox ? 'text-muted' : 'font-medium text-ink'}>
                {fromInbox ? 'It’s back in your Inbox.' : 'What should happen to it?'}
              </span>
              <Button size="xs" pending={action.pending}
                onClick={() => call(() => put(`/tasks/${task.id}/schedule`, { planned_date: nextDay }), `Moved to ${formatShort(nextDay)}`)}>
                Move to {nextDay === today ? 'today' : 'tomorrow'}
              </Button>
              {!fromInbox && <>
                <Button size="xs" pending={action.pending}
                  onClick={() => call(() => post(`/plans/${plan.id}/follow-up`, { action: 'unscheduled' }), 'Moved to the Inbox')}>Move to Inbox</Button>
                <Button size="xs" variant="ghost" pending={action.pending}
                  onClick={() => call(() => post(`/plans/${plan.id}/follow-up`, { action: 'leave' }), 'Left on this day')}>Leave it here</Button>
              </>}
            </div>
          )}
          {plan.follow_up === 'left' && !plan.carried_to_date && task.status === 'active' && !task.planned_date && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
              Left on this day.
              <Button size="xs" variant="ghost" pending={action.pending}
                onClick={() => call(() => post(`/plans/${plan.id}/follow-up`, { action: 'unscheduled' }), 'Moved to the Inbox')}>Move to Inbox</Button>
            </div>
          )}
          {plan.follow_up === 'unscheduled' && !plan.carried_to_date && !task.planned_date && (
            <p className="mt-1.5 text-xs text-muted">In your Inbox.</p>
          )}
        </div>
      )}

      {askReason && <NotDoneForm plan={plan} onCancel={() => setAskReason(false)} onSaved={() => { setAskReason(false); changed(notDoneMessage()) }} />}

      {more && (
        <div className="mt-2 flex flex-wrap gap-1 border-t border-line pt-2">
          {movable && <>
            <Button size="xs" onClick={() => { setMore(false); setDialog('move') }}>Time / move to date</Button>
            <Button size="xs" onClick={() => call(() => put(`/tasks/${task.id}/schedule`, { planned_date: null }), 'Moved back to the Inbox')}>Back to Inbox</Button>
          </>}
          {plan.state !== 'cancelled' && <Button size="xs" onClick={() => { setMore(false); setDialog('edit') }}>Edit</Button>}
          {movable && aiEnabled && <Button size="xs" onClick={() => { setMore(false); setDialog('breakdown') }}>Break down (AI)</Button>}
          <Button size="xs" onClick={() => { setMore(false); setDialog('history') }}>History</Button>
          {movable && (
            <Button size="xs" variant="danger" title={CANCEL_EXPLANATION}
              onClick={() => call(() => post(`/tasks/${task.id}/cancel`), 'Task cancelled (not counted)')}>Cancel task</Button>
          )}
          <Button size="xs" variant="danger" onClick={() => { setMore(false); setDialog('delete') }}>Delete task</Button>
        </div>
      )}
      {action.error && <div className="mt-2"><ErrorNote message={action.error} /></div>}

      {dialog === 'move' && (
        <MoveToDateDialog title={`When: “${task.title}”`} initialDate={plan.plan_date} initialStart={plan.planned_time} initialEnd={plan.planned_end_time}
          confirmLabel="Save"
          description={plan.plan_date < today ? 'This earlier day keeps its record (shown as awaiting review). The task continues on the new day.' : undefined}
          pending={action.pending} error={action.error} onClose={() => setDialog(null)}
          onConfirm={async (d, t) => {
            if (await action.run(() => put(`/tasks/${task.id}/schedule`, { planned_date: d, ...t })) !== undefined) {
              setDialog(null); changed(d === plan.plan_date ? `Time set to ${formatTimeRange(t.planned_time, t.planned_end_time)}` : `Moved to ${formatShort(d)}`)
            }
          }} />
      )}
      {dialog === 'edit' && <TaskFormDialog task={task} plan={plan} onClose={() => setDialog(null)} onSaved={() => onChanged()} />}
      {dialog === 'history' && <TaskHistoryDialog taskId={task.id} onClose={() => setDialog(null)} />}
      {dialog === 'delete' && <DeleteTaskDialog task={task} onClose={() => setDialog(null)} onDeleted={onChanged} />}
      {dialog === 'breakdown' && (
        <BreakdownDialog task={task} onClose={() => setDialog(null)}
          onApplied={() => { setDialog(null); changed('Task split into smaller tasks') }} />
      )}
    </li>
  )
}

function stateText(plan: Plan): string {
  if (plan.state === 'completed') return '✓ Completed'
  if (plan.state === 'not_completed' || plan.state === 'partial') return '✗ Not completed'
  if (plan.state === 'cancelled') return 'Cancelled'
  if (plan.state === 'awaiting_review') return 'Not marked yet'
  return ''
}

/** "Not completed" always needs a short written reason. Tags are optional shortcuts. */
function NotDoneForm({ plan, onCancel, onSaved }: { plan: Plan; onCancel: () => void; onSaved: () => void }) {
  const [note, setNote] = useState('')
  const [tag, setTag] = useState<Reason | null>(null)
  const [tried, setTried] = useState(false)
  const action = useAction()
  const valid = note.trim().length >= 3
  const save = async () => {
    setTried(true)
    if (!valid) return
    const r = await action.run(() => put(`/plans/${plan.id}/review`, { outcome: 'not_completed', reason: tag, reason_note: note.trim() }))
    if (r) onSaved()
  }
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-lg border border-danger/25 bg-danger-soft/40 p-3">
      <label htmlFor={`why-${plan.id}`} className="text-sm font-medium">Why wasn’t it done? <span className="text-danger">(required)</span></label>
      <textarea id={`why-${plan.id}`} className={inputClass} rows={2} maxLength={2000} autoFocus value={note}
        aria-invalid={tried && !valid} aria-describedby={`why-help-${plan.id}`}
        placeholder="e.g. Meetings ran over and I ran out of time"
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save(); if (e.key === 'Escape') onCancel() }} />
      {tried && !valid && <p id={`why-help-${plan.id}`} className="text-xs text-danger">Please write a short reason (at least 3 characters).</p>}
      <fieldset>
        <legend className="mb-1 text-xs text-muted">Tag it (optional, used in insights)</legend>
        <div className="flex flex-wrap gap-1">
          {REASONS.map((r) => (
            <label key={r.value} className={cx('cursor-pointer rounded-full border px-2.5 py-0.5 text-xs',
              tag === r.value ? 'border-accent bg-accent-soft text-accent' : 'border-line bg-card')}>
              <input type="radio" name={`tag-${plan.id}`} className="sr-only" checked={tag === r.value}
                onChange={() => setTag(tag === r.value ? null : r.value)} onClick={() => tag === r.value && setTag(null)} />
              {r.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex gap-2">
        <Button size="sm" variant="primary" pending={action.pending} onClick={save}>Save as not completed</Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
      {action.error && <ErrorNote message={action.error} />}
    </div>
  )
}
