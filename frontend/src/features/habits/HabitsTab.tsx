import { useState } from 'react'
import { get } from '../../api'
import { Badge, Button, Card, Empty, ErrorNote, Loading } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort } from '../../dates'
import { useLoad, useOnChanged } from '../../hooks'
import type { Habit, HabitDay, HabitDayItem } from '../../types'
import { CheckinControl } from './CheckinControl'
import { HabitCalendar } from './HabitCalendar'
import { EditHabitDialog, NewHabitDialog } from './HabitForm'
import { HabitInsights } from './HabitInsights'
import { describeSchedule } from './ScheduleEditor'

const STATUS: Record<string, { label: string; tone: 'accent' | 'warn' | 'danger' | 'neutral' }> = {
  done: { label: 'Done', tone: 'accent' },
  pending: { label: 'Not yet', tone: 'neutral' },
  missed: { label: 'Missed', tone: 'danger' },
  paused: { label: 'Paused', tone: 'warn' },
  not_scheduled: { label: 'Not scheduled', tone: 'neutral' },
  extra: { label: 'Extra', tone: 'accent' },
  open: { label: 'No session', tone: 'neutral' },
  future: { label: 'Upcoming', tone: 'neutral' },
  inactive: { label: 'Inactive', tone: 'neutral' },
}

export function HabitsTab() {
  const { date, today } = useApp()
  const day = useLoad<HabitDay>((s) => get(`/habits/day?date=${date}`, s), `habits-${date}`)
  useOnChanged(['habits'], day.reload)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Habit | null>(null)
  const d = day.data?.date === date ? day.data : null
  const future = date > today
  const empty = d && d.scheduled.length + d.weekly.length + d.other.length === 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-muted">Habits are tracked separately from tasks; their numbers are never combined.</p>
        <Button variant="primary" className="ml-auto" onClick={() => setCreating(true)}>+ New habit</Button>
      </div>
      {day.error && <ErrorNote message={day.error} onRetry={day.reload} />}
      {!d && !day.error && <Loading />}
      {empty && <Empty title="No habits yet">Create one to start tracking. Habits can be daily, on chosen weekdays, or a number of times per week.</Empty>}
      {d && !empty && (
        <>
          <Card aria-label="Scheduled habits">
            <div className="mb-3 flex flex-wrap items-baseline gap-2">
              <h3 className="font-semibold">Scheduled for this day</h3>
              {d.progress.scheduled > 0 && (
                <p className="text-sm text-muted">
                  {d.progress.done} of {d.progress.scheduled} done{d.progress.pct !== null && ` · ${d.progress.pct}%`}
                </p>
              )}
            </div>
            {d.scheduled.length === 0 ? <p className="text-sm text-muted">No habits are scheduled on this day.</p> : (
              <ul className="flex flex-col gap-2">{d.scheduled.map((i) => <HabitRow key={i.habit.id} item={i} date={date} future={future} onEdit={setEditing} onChanged={day.reload} />)}</ul>
            )}
          </Card>
          {d.weekly.length > 0 && (
            <Card aria-label="Weekly targets">
              <h3 className="font-semibold">Weekly targets</h3>
              <p className="mb-3 text-sm text-muted">Any day counts toward the week. These never show daily misses.</p>
              <ul className="flex flex-col gap-2">{d.weekly.map((i) => <HabitRow key={i.habit.id} item={i} date={date} future={future} onEdit={setEditing} onChanged={day.reload} />)}</ul>
            </Card>
          )}
          {d.other.length > 0 && (
            <Card aria-label="Other habits">
              <h3 className="mb-1 font-semibold">Not scheduled or paused today</h3>
              <p className="mb-3 text-sm text-muted">Nothing here counts as missed. You can still log an extra check-in.</p>
              <ul className="flex flex-col gap-2">{d.other.map((i) => <HabitRow key={i.habit.id} item={i} date={date} future={future} onEdit={setEditing} onChanged={day.reload} />)}</ul>
            </Card>
          )}
        </>
      )}
      <HabitCalendar />
      <HabitInsights />
      <ArchivedHabits onEdit={setEditing} />
      {creating && <NewHabitDialog onClose={() => setCreating(false)} />}
      {editing && <EditHabitDialog habit={editing} onClose={() => { setEditing(null); day.reload() }} />}
    </div>
  )
}

function HabitRow({ item, date, future, onEdit, onChanged }: {
  item: HabitDayItem; date: string; future: boolean; onEdit: (h: Habit) => void; onChanged: () => void
}) {
  const s = STATUS[item.status] ?? STATUS.inactive
  const schedule = item.habit.current_schedule
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border border-line px-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{item.habit.name}</span>
          <Badge tone={s.tone}>{s.label}</Badge>
          {item.streak && item.streak.value > 0 && (
            <Badge tone="accent" title="Counts scheduled days (or weeks for weekly targets); paused and unscheduled days are skipped">
              {item.streak.value} {item.streak.unit === 'weeks' ? 'week' : 'day'}{item.streak.value === 1 ? '' : 's'} streak
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted">{describeSchedule(schedule, item.habit.kind, item.habit.unit)}</p>
        {item.week && (
          <div className="mt-1.5 max-w-xs">
            <div className="flex justify-between text-xs">
              <span>{item.week.sessions} of {item.week.required} this week{item.week.required !== item.week.target && ` (scaled from ${item.week.target} for a partial week)`}</span>
              {item.week.met && <span className="text-accent">target met</span>}
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-ink/10" role="progressbar" aria-label={`${item.habit.name} weekly progress`}
              aria-valuemin={0} aria-valuemax={item.week.required} aria-valuenow={Math.min(item.week.sessions, item.week.required)}>
              <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, (item.week.sessions / Math.max(1, item.week.required)) * 100)}%` }} />
            </div>
          </div>
        )}
      </div>
      <CheckinControl item={item} date={date} disabled={future} onChanged={onChanged} />
      <Button size="sm" variant="ghost" onClick={() => onEdit(item.habit)} aria-label={`Edit ${item.habit.name}`}>Edit</Button>
    </li>
  )
}

function ArchivedHabits({ onEdit }: { onEdit: (h: Habit) => void }) {
  const [open, setOpen] = useState(false)
  const all = useLoad<Habit[]>((s) => (open ? get('/habits?include_archived=true', s) : Promise.resolve([])), `arch-${open}`)
  useOnChanged(['habits'], all.reload)
  const archived = all.data?.filter((h) => h.archived_on) ?? []
  return (
    <div>
      <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Hide archived habits' : 'Show archived habits'}</Button>
      {open && (
        <ul className="mt-2 flex flex-col gap-2">
          {archived.length === 0 && <li className="text-sm text-muted">No archived habits.</li>}
          {archived.map((h) => (
            <li key={h.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
              <span className="flex-1">{h.name} <span className="text-muted">· archived {formatShort(h.archived_on!)}</span></span>
              <Button size="sm" onClick={() => onEdit(h)}>Open</Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
