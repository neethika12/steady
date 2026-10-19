import { get } from '../../api'
import { Badge, Dialog, ErrorNote, Loading } from '../../components/ui'
import { useApp } from '../../context'
import { formatDateTime, formatLong, formatMinutes } from '../../dates'
import { useLoad } from '../../hooks'
import type { TaskHistory } from '../../types'
import { FOLLOW_UP_LABEL, REASON_LABEL, STATE_LABEL } from './labels'

const ACTION_LABEL: Record<string, string> = {
  review: 'Reviewed', correction: 'Correction', moved: 'Moved (before the day ended)',
  carried_forward: 'Carried forward', scheduled: 'Scheduled', plan_removed: 'Removed from a future day',
  cancelled: 'Cancelled', reopened: 'Reopened', archived: 'Archived', unarchived: 'Restored',
  split: 'Split', edited: 'Edited',
}

export function TaskHistoryDialog({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const { settings } = useApp()
  const h = useLoad<TaskHistory>((s) => get(`/tasks/${taskId}`, s), taskId)
  return (
    <Dialog title="Task history" onClose={onClose} wide>
      {h.error && <ErrorNote message={h.error} onRetry={h.reload} />}
      {h.loading && !h.data && <Loading />}
      {h.data && (
        <div className="flex flex-col gap-5">
          <div>
            <p className="font-semibold">{h.data.task.title}</p>
            {h.data.task.description && <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{h.data.task.description}</p>}
            <p className="mt-2 text-sm">Status: <strong>{h.data.task.status}</strong>
              {h.data.task.completed_at && <> · completed {formatDateTime(h.data.task.completed_at, settings.timezone)}</>}
              {h.data.task.estimated_minutes && <> · estimated {formatMinutes(h.data.task.estimated_minutes)}</>}
              {h.data.task.actual_minutes !== null && <> · actual {formatMinutes(h.data.task.actual_minutes)}</>}
            </p>
          </div>
          <section>
            <h3 className="mb-2 text-sm font-semibold">Days planned</h3>
            {h.data.plans.length === 0 ? <p className="text-sm text-muted">Never planned for a day.</p> : (
              <ol className="flex flex-col gap-2">
                {h.data.plans.map((p) => (
                  <li key={p.id} className="rounded-lg border border-line px-3 py-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{formatLong(p.plan_date)}</strong>
                      <Badge>{STATE_LABEL[p.state]}</Badge>
                      {p.carried_from_date && <Badge tone="accent">carried forward</Badge>}
                    </div>
                    {p.reason && <p className="text-muted">Reason: {REASON_LABEL[p.reason]}{p.reason_note && ` · “${p.reason_note}”`}</p>}
                    {p.follow_up && <p className="text-muted">Next step: {FOLLOW_UP_LABEL[p.follow_up]}</p>}
                    {p.completed_at && <p className="text-muted">Marked done {formatDateTime(p.completed_at, settings.timezone)}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
          {h.data.children.length > 0 && (
            <section>
              <h3 className="mb-2 text-sm font-semibold">Split into</h3>
              <ul className="list-inside list-disc text-sm">{h.data.children.map((c) => <li key={c.id}>{c.title} ({c.status})</li>)}</ul>
            </section>
          )}
          <section>
            <h3 className="mb-2 text-sm font-semibold">Change log</h3>
            <p className="mb-2 text-xs text-muted">Every review, correction and move is recorded here and never deleted.</p>
            <ol className="flex flex-col gap-1 text-sm">
              {h.data.audit.map((a) => (
                <li key={a.id} className="flex flex-wrap gap-x-2">
                  <span className="text-muted">{formatDateTime(a.created_at, settings.timezone)}</span>
                  <span>{ACTION_LABEL[a.action] ?? a.action}</span>
                  {a.action === 'correction' && a.before && a.after && (
                    <span className="text-muted">
                      {String(a.before.outcome ?? 'not reviewed')} → {String(a.after.outcome ?? 'not reviewed')}
                    </span>
                  )}
                  {a.note && <span className="text-muted">· {a.note}</span>}
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </Dialog>
  )
}
