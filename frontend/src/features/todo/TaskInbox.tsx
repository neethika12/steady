import { useState } from 'react'
import { errorMessage, get, newId, post, put } from '../../api'
import { MoveToDateDialog } from '../../components/MoveToDateDialog'
import { Button, ErrorNote, Loading, inputClass, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { formatMinutes, formatShort } from '../../dates'
import { notifyChanged, useAction, useLoad, useOnChanged } from '../../hooks'
import type { Plan, Task } from '../../types'
import { BreakdownDialog } from '../ai/BreakdownDialog'
import { useAiEnabled } from '../ai/AiStatus'
import { DeleteTaskDialog } from './DeleteTaskDialog'
import { STATE_LABEL } from './labels'
import { setTaskDragData } from './dropToDay'
import { TaskFormDialog } from './TaskForm'
import { TaskHistoryDialog } from './TaskHistory'

/**
 * The Inbox: every active task without a day, always shown beside the planner.
 * Capture here, then drag a task onto a day (or use "Move to date").
 */
/** Phones and tablets: an "Inbox" button that opens the Inbox full screen. */
export function InboxButton() {
  const tasks = useLoad<Task[]>((s) => get('/tasks?view=inbox', s), 'inbox-count')
  useOnChanged(['tasks'], tasks.reload)
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button className="lg:hidden" onClick={() => setOpen(true)} aria-haspopup="dialog">
        Inbox{tasks.data ? <span className="ml-1 rounded bg-ink/10 px-1.5 text-xs tabular-nums">{tasks.data.length}</span> : null}
      </Button>
      {open && (
        <div role="dialog" aria-modal="true" aria-label="Inbox" onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
          className="fixed inset-0 z-40 overflow-y-auto bg-night pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] lg:hidden">
          <TaskInbox onClose={() => setOpen(false)} />
        </div>
      )}
    </>
  )
}

export function TaskInbox({ onClose }: { onClose?: () => void } = {}) {
  const tasks = useLoad<Task[]>((s) => get('/tasks?view=inbox', s), 'inbox-tasks')
  const waiting = useLoad<Plan[]>((s) => get('/plans/needs-decision', s), 'inbox-waiting')
  const [showAll, setShowAll] = useState(false)
  const reload = () => { tasks.reload(); waiting.reload() }
  useOnChanged(['tasks'], reload)

  // Most recent activity first: a new capture, or a task just back from a day, is always at the top.
  const unfinished = new Map(waiting.data?.map((p) => [p.task_id, p]))
  const list = [...(tasks.data ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  const shown = showAll ? list : list.slice(0, 30)

  return (
    <aside id={onClose ? undefined : 'task-inbox'} aria-label={onClose ? undefined : 'Inbox'}
      className="order-last min-h-full flex flex-col bg-night text-white lg:sticky lg:top-0 lg:order-first lg:h-dvh lg:w-80 lg:shrink-0 xl:w-96">
      <header className="flex flex-col gap-1.5 border-b border-white/10 px-5 pb-5 pt-6 text-white">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">Inbox</h2>
          {tasks.data && (
            <span className="ml-auto rounded-md bg-white/10 px-2 py-0.5 text-sm font-semibold tabular-nums text-white"
              aria-label={`${list.length} tasks without a day`}>{list.length}</span>
          )}
          {onClose && (
            <Button size="sm" className="border-white/25 bg-white/10 text-white hover:bg-white/20" onClick={onClose}>Close</Button>
          )}
        </div>
        <p className="text-xs leading-relaxed text-white/60">Tasks without a day. {onClose ? <>Tap <span className="text-white/85">Plan</span> to give one a day and time.</> : <>Drag one onto a day, or use <span className="text-white/85">Move to date</span>.</>}</p>
        <div className="mt-1.5"><QuickCapture onSaved={reload} /></div>
      </header>
      <div className="flex flex-1 flex-col gap-2 px-4 py-4 lg:overflow-y-auto">
        {(tasks.error || waiting.error) && <ErrorNote message={(tasks.error || waiting.error)!} onRetry={reload} />}
        {tasks.loading && !tasks.data && <Loading />}
        {tasks.data && list.length === 0 && (
          <p className="rounded-lg border border-dashed border-white/20 px-3 py-6 text-center text-sm text-white/60">
            Inbox is clear. Type a task above to capture it without a date.
          </p>
        )}
        <ul className="flex flex-col gap-2" aria-label="Tasks without a day">
          {shown.map((t) => <InboxTask key={t.id} task={t} unfinished={unfinished.get(t.id)} onChanged={reload} />)}
        </ul>
        {list.length > 30 && (
          <Button size="xs" variant="ghost" className="text-white/75 hover:bg-white/10 hover:text-white" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
            {showAll ? 'Show fewer' : `Show all ${list.length}`}
          </Button>
        )}
      </div>
    </aside>
  )
}

function QuickCapture({ onSaved }: { onSaved: () => void }) {
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(0)
  const [error, setError] = useState<string | null>(null)
  // Each entry is saved on its own, so you can type the next one straight away.
  // The client-generated id makes a retried request safe: it can't create a duplicate.
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const value = text.trim()
    if (!value) return
    setText('')
    setError(null)
    setSaving((n) => n + 1)
    try {
      await post<Task>('/tasks', {
        id: newId(), title: value.slice(0, 200), description: value.length > 200 ? value : '',
      })
      notifyChanged('tasks')
      onSaved()
    } catch (err) {
      setText((current) => (current.trim() ? `${current} ${value}` : value)) // never lose what was typed
      setError(errorMessage(err))
    } finally {
      setSaving((n) => n - 1)
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-1.5">
      <div className="flex gap-1.5">
        <label htmlFor="capture" className="sr-only">Capture a task</label>
        <input id="capture" className={`${inputClass} border-white/10 bg-white/95 text-ink`} placeholder="Capture a task…" value={text}
          maxLength={5000} onChange={(e) => setText(e.target.value)} autoComplete="off" />
        <Button type="submit" variant="primary" disabled={!text.trim()}>Add</Button>
      </div>
      {saving > 0 && <span className="text-xs text-white/70">Saving…</span>}
      {error && <ErrorNote message={`Couldn't save: ${error} Your text has been put back in the box.`} />}
    </form>
  )
}

function InboxTask({ task, unfinished, onChanged }: { task: Task; unfinished?: Plan; onChanged: () => void }) {
  const aiEnabled = useAiEnabled()
  const { today } = useApp()
  const [more, setMore] = useState(false)
  const [dialog, setDialog] = useState<'move' | 'edit' | 'history' | 'breakdown' | 'delete' | null>(null)
  const action = useAction()
  const toast = useToast()
  const changed = (msg: string) => { toast(msg); notifyChanged('tasks'); onChanged() }
  const call = async (fn: () => Promise<unknown>, msg: string) => { if (await action.run(fn) !== undefined) changed(msg) }
  const overdue = task.deadline && task.deadline < today

  return (
    <li
      draggable
      onDragStart={(e) => setTaskDragData(e, task.id, task.estimated_minutes)}
      className="group cursor-grab rounded-lg bg-card px-3 py-2.5 text-ink shadow-sm ring-1 ring-black/5 transition hover:ring-2 hover:ring-accent/60 active:cursor-grabbing"
    >
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            {task.priority === 'high' && <span aria-label="High priority" className="size-1.5 shrink-0 rounded-full bg-sun" />}
            <span className="line-clamp-2 break-words">{task.title}</span>
          </p>
          {(unfinished || task.estimated_minutes || task.deadline) && (
            <p className="mt-0.5 truncate text-xs text-muted">
              {[
                unfinished && <span key="u" className="text-danger" title="Marked not completed. Plan it again, keep it here, or cancel it.">{STATE_LABEL[unfinished.state]} · {formatShort(unfinished.plan_date)}</span>,
                task.estimated_minutes && <span key="e">~{formatMinutes(task.estimated_minutes)}</span>,
                task.deadline && <span key="d" className={overdue ? 'text-danger' : undefined}>Due {formatShort(task.deadline)}</span>,
              ].filter(Boolean).flatMap((el, i) => (i ? [<span key={`s${i}`}> · </span>, el] : [el]))}
            </p>
          )}
        </div>
        <Button size="xs" variant="ghost" aria-label="Move to date" title="Plan it on a day"
          className="shrink-0 text-accent opacity-70 group-hover:opacity-100" onClick={() => { setMore(false); setDialog('move') }}>Plan</Button>
        <Button size="xs" variant="ghost" aria-expanded={more} aria-label={`More actions for ${task.title}`}
          className="shrink-0 opacity-60 group-hover:opacity-100" onClick={() => setMore(!more)}>⋯</Button>
      </div>
      {more && (
        <div className="mt-2 flex flex-wrap gap-0.5 border-t border-line pt-1.5">
          <Button size="xs" variant="ghost" onClick={() => { setMore(false); setDialog('edit') }}>Edit</Button>
          {unfinished && (
            <Button size="xs" variant="ghost" pending={action.pending} title="Keep it in the Inbox without a date"
              onClick={() => call(() => post(`/plans/${unfinished.id}/follow-up`, { action: 'unscheduled' }), 'Kept in Inbox')}>Keep for later</Button>
          )}
          {aiEnabled && <Button size="xs" variant="ghost" onClick={() => { setMore(false); setDialog('breakdown') }}>Break down (AI)</Button>}
          <Button size="xs" variant="ghost" onClick={() => { setMore(false); setDialog('history') }}>History</Button>
          <Button size="xs" variant="danger" pending={action.pending}
            onClick={() => call(() => unfinished
              ? post(`/plans/${unfinished.id}/follow-up`, { action: 'cancel' })
              : post(`/tasks/${task.id}/cancel`), 'Task cancelled')}>Cancel task</Button>
          <Button size="xs" variant="danger" onClick={() => { setMore(false); setDialog('delete') }}>Delete task</Button>
        </div>
      )}
      {action.error && <div className="mt-1"><ErrorNote message={action.error} /></div>}

      {dialog === 'move' && (
        <MoveToDateDialog title={`Plan “${task.title}”`} confirmLabel="Plan" pending={action.pending} error={action.error}
          description={unfinished ? `${formatShort(unfinished.plan_date)} keeps its record; the task is carried forward to the new day.` : undefined}
          onClose={() => setDialog(null)}
          onConfirm={async (d, t) => {
            if (await action.run(() => put(`/tasks/${task.id}/schedule`, { planned_date: d, ...t })) !== undefined) {
              setDialog(null); changed(`Planned for ${formatShort(d)}`)
            }
          }} />
      )}
      {dialog === 'edit' && <TaskFormDialog task={task} onClose={() => setDialog(null)} onSaved={onChanged} />}
      {dialog === 'history' && <TaskHistoryDialog taskId={task.id} onClose={() => setDialog(null)} />}
      {dialog === 'delete' && <DeleteTaskDialog task={task} onClose={() => setDialog(null)} onDeleted={onChanged} />}
      {dialog === 'breakdown' && (
        <BreakdownDialog task={task} onClose={() => setDialog(null)}
          onApplied={() => { setDialog(null); changed('Split into smaller tasks') }} />
      )}
    </li>
  )
}
