import { useState } from 'react'
import { newId, patch, post, put } from '../../api'
import { Badge, Button, Dialog, ErrorNote, Field, fieldBase, inputClass, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import type { Habit, HabitKind, ScheduleInput } from '../../types'
import { KindPicker, ScheduleEditor, defaultSchedule, describeSchedule, scheduleIsValid } from './ScheduleEditor'

export function NewHabitDialog({ onClose }: { onClose: () => void }) {
  const { today } = useApp()
  const [id] = useState(newId)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [kind, setKind] = useState<HabitKind>('boolean')
  const [unit, setUnit] = useState('')
  const [start, setStart] = useState(today)
  const [schedule, setSchedule] = useState<ScheduleInput>(defaultSchedule)
  const { run, pending, error } = useAction()
  const toast = useToast()
  const submit = async () => {
    const r = await run(() => post<Habit>('/habits', {
      id, name: name.trim(), description, kind, unit: kind === 'count' ? unit : null, start_date: start, schedule,
    }))
    if (r) { toast('Habit created'); notifyChanged('habits'); onClose() }
  }
  return (
    <Dialog title="New habit" onClose={onClose} footer={<>
      <Button onClick={onClose}>Cancel</Button>
      <Button variant="primary" pending={pending} disabled={!name.trim() || !scheduleIsValid(schedule)} onClick={submit}>Create habit</Button>
    </>}>
      <div className="flex flex-col gap-4">
        <Field label="Name" htmlFor="nh-name">
          <input id="nh-name" className={inputClass} value={name} maxLength={120} autoFocus placeholder="e.g. Read" onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Description (optional)" htmlFor="nh-desc">
          <input id="nh-desc" className={inputClass} value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <KindPicker kind={kind} onChange={setKind} />
        {kind === 'count' && (
          <Field label="Unit (optional)" htmlFor="nh-unit"><input id="nh-unit" className={inputClass} value={unit} maxLength={30} placeholder="e.g. glasses" onChange={(e) => setUnit(e.target.value)} /></Field>
        )}
        <ScheduleEditor value={schedule} onChange={setSchedule} kind={kind} unit={unit} idPrefix="nh" />
        <Field label="Starts on" htmlFor="nh-start" hint="Days before this are never counted.">
          <input id="nh-start" type="date" className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        {error && <ErrorNote message={error} />}
      </div>
    </Dialog>
  )
}

export function EditHabitDialog({ habit, onClose }: { habit: Habit; onClose: () => void }) {
  const { today } = useApp()
  const [name, setName] = useState(habit.name)
  const [description, setDescription] = useState(habit.description)
  const [unit, setUnit] = useState(habit.unit ?? '')
  const current = habit.current_schedule
  const [schedule, setSchedule] = useState<ScheduleInput>(current
    ? { schedule_type: current.schedule_type, weekdays: current.weekdays, weekly_target: current.weekly_target, target_value: current.target_value }
    : defaultSchedule)
  const latestStart = habit.schedules.at(-1)?.effective_from ?? habit.start_date
  const [from, setFrom] = useState(today < latestStart ? latestStart : today)
  const [pauseStart, setPauseStart] = useState(today)
  const [pauseEnd, setPauseEnd] = useState('')
  const action = useAction()
  const toast = useToast()
  const done = (msg: string) => { toast(msg); notifyChanged('habits') }
  const openPause = habit.pauses.find((p) => p.end_date === null || p.end_date >= today)

  return (
    <Dialog title={`Edit “${habit.name}”`} onClose={onClose} wide footer={<Button onClick={onClose}>Close</Button>}>
      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">Details</h3>
          <Field label="Name" htmlFor="eh-name"><input id="eh-name" className={inputClass} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Description" htmlFor="eh-desc"><input id="eh-desc" className={inputClass} value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} /></Field>
          {habit.kind === 'count' && <Field label="Unit" htmlFor="eh-unit"><input id="eh-unit" className={inputClass} value={unit} maxLength={30} onChange={(e) => setUnit(e.target.value)} /></Field>}
          <div><Button variant="primary" size="sm" pending={action.pending} disabled={!name.trim()} onClick={async () => {
            if (await action.run(() => patch(`/habits/${habit.id}`, { name, description, unit: habit.kind === 'count' ? unit : null }))) done('Saved')
          }}>Save details</Button></div>
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">Schedule</h3>
          <p className="text-sm text-muted">
            A change applies from the date you choose. Earlier days keep being judged by the schedule they had, so past results don’t change.
          </p>
          <ScheduleEditor value={schedule} onChange={setSchedule} kind={habit.kind} unit={habit.unit} idPrefix="eh" />
          <Field label="Applies from" htmlFor="eh-from" hint={`Earliest allowed: ${formatShort(latestStart)}`}>
            <input id="eh-from" type="date" min={latestStart} className={`${fieldBase} w-auto`} value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <div><Button size="sm" variant="primary" pending={action.pending} disabled={!scheduleIsValid(schedule) || !from} onClick={async () => {
            if (await action.run(() => put(`/habits/${habit.id}/schedule`, { schedule, effective_from: from }))) done('Schedule updated')
          }}>Change schedule</Button></div>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted">Schedule history ({habit.schedules.length})</summary>
            <ul className="mt-2 flex flex-col gap-1">
              {habit.schedules.map((s) => (
                <li key={s.id}>{formatShort(s.effective_from)} → {s.effective_to ? formatShort(s.effective_to) : 'now'}: {describeSchedule(s, habit.kind, habit.unit)}</li>
              ))}
            </ul>
          </details>
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">Pause</h3>
          <p className="text-sm text-muted">Paused days never count as missed and don’t break streaks.</p>
          {openPause ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="warn">Paused from {formatShort(openPause.start_date)}{openPause.end_date ? ` to ${formatShort(openPause.end_date)}` : ' until resumed'}</Badge>
              <Button size="sm" pending={action.pending} onClick={async () => {
                if (await action.run(() => post(`/habits/${habit.id}/resume`, {}))) done('Resumed from today')
              }}>Resume today</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <Field label="From" htmlFor="eh-ps"><input id="eh-ps" type="date" className={`${fieldBase} w-auto`} value={pauseStart} onChange={(e) => setPauseStart(e.target.value)} /></Field>
              <Field label="Until (optional)" htmlFor="eh-pe"><input id="eh-pe" type="date" className={`${fieldBase} w-auto`} value={pauseEnd} min={pauseStart} onChange={(e) => setPauseEnd(e.target.value)} /></Field>
              <Button size="sm" pending={action.pending} onClick={async () => {
                if (await action.run(() => post(`/habits/${habit.id}/pause`, { start_date: pauseStart, end_date: pauseEnd || null }))) done('Habit paused')
              }}>Pause</Button>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="font-semibold">Archive</h3>
          <p className="text-sm text-muted">Archiving hides the habit from now on. Its check-ins and history are kept.</p>
          <div>
            {habit.archived_on ? (
              <Button size="sm" pending={action.pending} onClick={async () => {
                if (await action.run(() => post(`/habits/${habit.id}/unarchive`))) done('Habit restored')
              }}>Restore habit</Button>
            ) : (
              <Button size="sm" variant="danger" pending={action.pending} onClick={async () => {
                if (await action.run(() => post(`/habits/${habit.id}/archive`))) { done('Habit archived'); onClose() }
              }}>Archive habit</Button>
            )}
          </div>
        </section>
        {action.error && <ErrorNote message={action.error} />}
      </div>
    </Dialog>
  )
}
