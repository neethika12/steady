import { useState } from 'react'
import { get } from '../../api'
import { Button, Disclosure, Empty, ErrorNote, Loading, cx } from '../../components/ui'
import { useApp } from '../../context'
import { WEEKDAY_SHORT, addDays, formatLong, formatMonth, weekdayIndex } from '../../dates'
import { useLoad, useOnChanged } from '../../hooks'
import type { HabitCalendarRow, HabitDayStatus } from '../../types'

const STYLE: Record<HabitDayStatus, string> = {
  done: 'bg-accent text-white',
  extra: 'bg-accent/40 text-ink',
  missed: 'bg-danger-soft text-danger border border-danger/30',
  pending: 'border-2 border-accent/60',
  paused: 'bg-warn-soft text-warn',
  open: 'bg-ink/5',
  not_scheduled: 'bg-transparent text-muted/50',
  inactive: 'bg-transparent text-muted/30',
  future: 'bg-transparent text-muted/50',
}
const LABEL: Record<HabitDayStatus, string> = {
  done: 'done', extra: 'done (not scheduled)', missed: 'missed', pending: 'today, not done yet',
  paused: 'paused', open: 'no session', not_scheduled: 'not scheduled', inactive: 'not active', future: 'upcoming',
}

function monthBounds(iso: string) {
  const first = iso.slice(0, 8) + '01'
  const next = addDays(first, 32).slice(0, 8) + '01'
  return { first, last: addDays(next, -1) }
}

export function HabitCalendar() {
  const { date, settings } = useApp()
  const [anchor, setAnchor] = useState(date)
  const { first, last } = monthBounds(anchor)
  const data = useLoad<HabitCalendarRow[]>((s) => get(`/habits/calendar?start=${first}&end=${last}`, s), `cal-${first}`)
  useOnChanged(['habits'], data.reload)
  const lead = (weekdayIndex(first) - settings.week_start + 7) % 7
  const headers = Array.from({ length: 7 }, (_, i) => WEEKDAY_SHORT[(settings.week_start + i) % 7])

  return (
    <Disclosure title="Consistency calendar">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Button size="sm" aria-label="Previous month" onClick={() => setAnchor(addDays(first, -1))}>‹</Button>
          <p className="min-w-36 text-center font-medium" aria-live="polite">{formatMonth(first)}</p>
          <Button size="sm" aria-label="Next month" onClick={() => setAnchor(addDays(last, 1))}>›</Button>
        </div>
        <ul className="flex flex-wrap gap-3 text-xs text-muted" aria-label="Legend">
          {(['done', 'extra', 'missed', 'paused', 'open', 'not_scheduled'] as HabitDayStatus[]).map((s) => (
            <li key={s} className="flex items-center gap-1"><span className={cx('inline-block size-3 rounded-sm', STYLE[s], s === 'not_scheduled' && 'border border-line')} />{LABEL[s]}</li>
          ))}
        </ul>
        <p className="text-xs text-muted">Paused and unscheduled days are never counted as missed. Weekly-target habits show sessions only; they are judged per week.</p>
        {data.error && <ErrorNote message={data.error} onRetry={data.reload} />}
        {data.loading && !data.data && <Loading />}
        {data.data?.length === 0 && <Empty title="No habits in this month" />}
        <div className="grid gap-4 sm:grid-cols-2">
          {data.data?.map((row) => (
            <figure key={row.habit.id} className="rounded-lg border border-line p-3">
              <figcaption className="mb-2 text-sm font-medium">{row.habit.name}</figcaption>
              <div role="grid" aria-label={`${row.habit.name}, ${formatMonth(first)}`} className="grid grid-cols-7 gap-1 text-center text-[11px]">
                {headers.map((h) => <span key={h} role="columnheader" className="text-muted">{h[0]}</span>)}
                {Array.from({ length: lead }, (_, i) => <span key={`l${i}`} />)}
                {row.days.map((d) => (
                  <span key={d.date} role="gridcell" title={`${formatLong(d.date)}: ${LABEL[d.status]}${d.value !== null ? ` (${d.value})` : ''}`}
                    aria-label={`${formatLong(d.date)}: ${LABEL[d.status]}`}
                    className={cx('grid aspect-square place-items-center rounded-md', STYLE[d.status])}>
                    {Number(d.date.slice(8))}
                  </span>
                ))}
              </div>
            </figure>
          ))}
        </div>
      </div>
    </Disclosure>
  )
}
