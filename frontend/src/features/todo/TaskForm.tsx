import { useState } from 'react'
import { newId, patch, post, put } from '../../api'
import { TimeChoice, initialTime, timeError, timePayload, type TimeValue } from '../../components/MoveToDateDialog'
import { Button, Dialog, ErrorNote, Field, Segmented, inputClass, useToast } from '../../components/ui'
import { notifyChanged, useAction } from '../../hooks'
import type { Plan, Priority, Task } from '../../types'
import { useApp } from '../../context'
import { timelineSpan } from '../../dates'

/** Create a task (optionally planned for a day and time) or edit an existing one, including its day and time. */
export function TaskFormDialog({ task, plan, plannedDate, initialStart, initialEnd, initialPriority, onClose, onSaved }: {
  task?: Task; plan?: Plan; plannedDate?: string | null; initialPriority?: Priority
  initialStart?: string | null; initialEnd?: string | null // e.g. from clicking the timeline
  onClose: () => void; onSaved?: (t: Task) => void
}) {
  const [id] = useState(newId) // fixed for this form: re-submitting can't duplicate
  const [title, setTitle] = useState(task?.title ?? '')
  const [description, setDescription] = useState(task?.description ?? '')
  const [priority, setPriority] = useState<Priority>(task?.priority ?? initialPriority ?? 'medium')
  const [category, setCategory] = useState(task?.category ?? '')
  const [estimate, setEstimate] = useState(task?.estimated_minutes?.toString() ?? '')
  const [actual, setActual] = useState(task?.actual_minutes?.toString() ?? '')
  const [deadline, setDeadline] = useState(task?.deadline ?? '')
  // Day and time can be set when creating, and changed later while the task is still open.
  const canPlan = !task || task.status === 'active'
  const currentPlan = task && plan && plan.plan_date === task.planned_date ? plan : undefined
  const startTime = task ? initialTime(currentPlan?.planned_time, currentPlan?.planned_end_time) : initialTime(initialStart, initialEnd)
  const [planned, setPlanned] = useState(task ? task.planned_date ?? '' : plannedDate ?? '')
  const [time, setTime] = useState<TimeValue>(startTime)
  const { run, pending, error } = useAction()
  const { settings } = useApp()
  const toast = useToast()
  const num = (v: string) => (v.trim() === '' ? null : Math.max(0, Math.round(Number(v))))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    const common = {
      title: title.trim(), description, priority, category: category.trim() || null,
      estimated_minutes: num(estimate) || null, deadline: deadline || null,
    }
    const saved = await run(async () => {
      if (!task) {
        return post<Task>('/tasks', { ...common, id, planned_date: planned || null, ...(planned ? timePayload(time) : {}) })
      }
      const updated = await patch<Task>(`/tasks/${task.id}`, { ...common, actual_minutes: num(actual) })
      const dayChanged = planned !== (task.planned_date ?? '')
      const timeChanged = !!planned && JSON.stringify(timePayload(time)) !== JSON.stringify(timePayload(startTime))
      if (canPlan && (dayChanged || timeChanged)) {
        // Same rules as "Move to date": earlier days keep their record; no day = the Inbox.
        return put<Task>(`/tasks/${task.id}/schedule`, planned ? { planned_date: planned, ...timePayload(time) } : { planned_date: null })
      }
      return updated
    })
    if (saved) {
      if (task) toast('Task updated') // a new task simply appears where it belongs
      notifyChanged('tasks')
      onSaved?.(saved)
      onClose()
    }
  }

  return (
    <Dialog title={task ? 'Edit task' : 'New task'} onClose={onClose} footer={<>
      <Button onClick={onClose}>Cancel</Button>
      <Button variant="primary" type="submit" form="task-form" pending={pending} disabled={!title.trim() || (canPlan && !!planned && !!timeError(time, timelineSpan(settings).pastMidnight))}>{task ? 'Save' : 'Add task'}</Button>
    </>}>
      <form id="task-form" onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Title" htmlFor="tf-title">
          <input id="tf-title" className={inputClass} value={title} maxLength={200} required autoFocus onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Description (optional)" htmlFor="tf-desc">
          <textarea id="tf-desc" className={inputClass} rows={3} value={description} maxLength={5000} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Priority">
          <Segmented label="Priority" value={priority} onChange={setPriority} options={[
            { value: 'high', label: 'High' }, { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' },
          ]} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category (optional)" htmlFor="tf-cat">
            <input id="tf-cat" className={inputClass} value={category} maxLength={60} placeholder="e.g. Work" onChange={(e) => setCategory(e.target.value)} />
          </Field>
          <Field label="Estimated minutes (optional)" htmlFor="tf-est">
            <input id="tf-est" type="number" min={1} max={1440} inputMode="numeric" className={inputClass} value={estimate} onChange={(e) => setEstimate(e.target.value)} />
          </Field>
          <Field label="Deadline (optional)" htmlFor="tf-deadline">
            <input id="tf-deadline" type="date" className={inputClass} value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </Field>
          {task && (
            <Field label="Actual minutes (optional)" htmlFor="tf-actual" hint="How long it really took, if you know.">
              <input id="tf-actual" type="number" min={0} max={10000} inputMode="numeric" className={inputClass} value={actual} onChange={(e) => setActual(e.target.value)} />
            </Field>
          )}
          {canPlan && (
            <Field label="Day (optional)" htmlFor="tf-planned"
              hint={task?.planned_date && !planned ? 'No day: it will move to the Inbox.' : 'Leave empty to keep it in the Inbox.'}>
              <input id="tf-planned" type="date" className={inputClass} value={planned} onChange={(e) => setPlanned(e.target.value)} />
            </Field>
          )}
        </div>
        {canPlan && planned && <TimeChoice value={time} onChange={setTime} idPrefix="tf" />}
        {error && <ErrorNote message={error} />}
      </form>
    </Dialog>
  )
}
