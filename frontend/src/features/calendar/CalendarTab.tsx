import { useState } from 'react'
import { get } from '../../api'
import { Button, ErrorNote, Loading } from '../../components/ui'
import { useApp } from '../../context'
import { formatLong } from '../../dates'
import { useLoad, useOnChanged } from '../../hooks'
import type { Day } from '../../types'
import { DayBoard } from '../todo/DayBoard'
import { TaskFormDialog } from '../todo/TaskForm'

/** The day as a calendar: drag tasks onto times, click or drag on empty time to create one. */
export function CalendarTab() {
  const { date } = useApp()
  const day = useLoad<Day>((s) => get(`/plans/day?date=${date}`, s), `cal-day-${date}`)
  useOnChanged(['tasks'], day.reload)
  const [creating, setCreating] = useState(false)
  const d = day.data?.date === date ? day.data : null
  return (
    <div aria-label={`Tasks for ${formatLong(date)}`} className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-muted">Your timed tasks for the day. Click or drag on empty time to add one, or drag a task to move it. Anytime tasks are in To-Do.</p>
        <Button variant="primary" className="ml-auto" onClick={() => setCreating(true)}>+ New task</Button>
      </div>
      {day.error && <ErrorNote message={day.error} onRetry={day.reload} />}
      {!d && !day.error && <Loading />}
      {d && <DayBoard date={date} plans={d.plans} onChanged={day.reload} mode="calendar" />}
      {creating && <TaskFormDialog plannedDate={date} onClose={() => setCreating(false)} onSaved={day.reload} />}
    </div>
  )
}
