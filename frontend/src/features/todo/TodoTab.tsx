import { useState } from 'react'
import { get } from '../../api'
import { Button, Card, ErrorNote, Loading, Notice, Segmented } from '../../components/ui'
import { useApp } from '../../context'
import { formatLong, formatShort, relativeLabel, weekDays } from '../../dates'
import { DateControls } from '../../components/DateBar'
import { useLoad, useOnChanged } from '../../hooks'
import type { Day, Week } from '../../types'
import { DailyPlanDialog } from '../ai/DailyPlanDialog'
import { InboxButton } from './TaskInbox'
import { useAiEnabled } from '../ai/AiStatus'
import { DayStatsSummary } from './DayStatsSummary'
import { DayBoard } from './DayBoard'
import { TaskFormDialog } from './TaskForm'
import { TaskInsights } from './TaskInsights'
import { WeekView } from './WeekView'

function readView(): 'day' | 'week' {
  try { return sessionStorage.getItem('steady.todoView') === 'week' ? 'week' : 'day' } catch { return 'day' }
}

export function TodoTab() {
  const aiEnabled = useAiEnabled()
  const { date, setDate, today, settings } = useApp()
  const [view, setViewState] = useState<'day' | 'week'>(readView)
  const [dialog, setDialog] = useState<'new' | 'plan' | null>(null)
  const pending = useLoad<{ date: string; unreviewed: number }[]>((s) => get('/plans/pending-reviews', s), 'pending')
  useOnChanged(['tasks'], pending.reload)

  const setView = (v: 'day' | 'week') => {
    setViewState(v)
    try { sessionStorage.setItem('steady.todoView', v) } catch { /* ignore */ }
  }
  const earlier = pending.data?.filter((p) => p.date !== date) ?? []

  const days = weekDays(date, settings.week_start)
  const rel = relativeLabel(date, today)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          {view === 'week' ? (days.includes(today) ? 'This week' : 'Week') : rel === 'Today' || rel === 'Yesterday' || rel === 'Tomorrow' ? rel : 'Selected day'}
        </p>
        <h2 className="text-lg font-semibold" aria-live="polite">
          {view === 'week' ? `${formatShort(days[0])} – ${formatShort(days[6])}` : formatLong(date)}
        </h2>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented label="To-Do view" value={view} onChange={setView} options={[
          { value: 'day', label: 'Day' }, { value: 'week', label: 'Week' },
        ]} />
        <DateControls step={view === 'week' ? 7 : 1} />
        <div className="ml-auto flex flex-wrap gap-2">
          <InboxButton />
          {view === 'day' && aiEnabled && <Button onClick={() => setDialog('plan')}>Suggest a plan (AI)</Button>}
          <Button variant="primary" onClick={() => setDialog('new')}>+ New task</Button>
        </div>
      </div>

      {earlier.length > 0 && (
        <Notice tone="warn">
          <span className="mr-2">Earlier days have tasks not marked yet:</span>
          {earlier.slice(0, 5).map((p) => (
            <button key={p.date} type="button" onClick={() => { setDate(p.date); setView('day') }} className="mr-2 font-medium underline underline-offset-2">
              {formatShort(p.date)} ({p.unreviewed})
            </button>
          ))}
        </Notice>
      )}

      {view === 'day' ? <DayPanel /> : (
        <WeekPanel onOpenDay={(d) => { setDate(d); setView('day') }} />
      )}
      <TaskInsights />

      {dialog === 'new' && <TaskFormDialog plannedDate={date} onClose={() => setDialog(null)} />}
      {dialog === 'plan' && <DailyPlanDialog date={date} onClose={() => setDialog(null)} />}
    </div>
  )
}


function DayPanel() {
  const { date, today } = useApp()
  const day = useLoad<Day>((s) => get(`/plans/day?date=${date}`, s), `day-${date}`)
  useOnChanged(['tasks'], day.reload)
  const d = day.data?.date === date ? day.data : null
  return (
    <div aria-label={`Tasks for ${formatLong(date)}`} className="flex min-w-0 flex-col gap-4">
      <Card aria-label="Day summary">
        {day.error && <ErrorNote message={day.error} onRetry={day.reload} />}
        {!d && !day.error && <Loading />}
        {d && <DayStatsSummary stats={d.stats} isPast={date < today} isToday={date === today} />}
      </Card>
      {d && <DayBoard date={date} plans={d.plans} onChanged={day.reload} mode="list" />}
    </div>
  )
}

function WeekPanel({ onOpenDay }: { onOpenDay: (d: string) => void }) {
  const { date } = useApp()
  const week = useLoad<Week>((s) => get(`/plans/week?date=${date}`, s), `week-${date}`)
  useOnChanged(['tasks'], week.reload)
  if (week.error) return <ErrorNote message={week.error} onRetry={week.reload} />
  if (!week.data) return <Loading />
  return <WeekView week={week.data} onChanged={week.reload} onOpenDay={onOpenDay} />
}
