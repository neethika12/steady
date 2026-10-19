import { useState } from 'react'
import { get } from '../../api'
import { Disclosure, ErrorNote, Loading, Segmented } from '../../components/ui'
import { useApp } from '../../context'
import { addDays, formatShort, weekStart } from '../../dates'
import { useLoad, useOnChanged } from '../../hooks'
import type { HabitInsights as Insights } from '../../types'
import { HabitReview } from '../ai/HabitReview'

export function HabitInsights() {
  const { date, settings } = useApp()
  const [range, setRange] = useState<'week' | 'four'>('four')
  const end = addDays(weekStart(date, settings.week_start), 6)
  const start = range === 'week' ? weekStart(date, settings.week_start) : addDays(end, -27)
  const data = useLoad<Insights>((s) => get(`/insights/habits?start=${start}&end=${end}`, s), `hi-${start}-${end}`)
  useOnChanged(['habits'], data.reload)
  const d = data.data
  return (
    <Disclosure title="Consistency insights">
      <div className="flex flex-col gap-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Insight range" size="sm" value={range} onChange={setRange} options={[
            { value: 'week', label: 'This week' }, { value: 'four', label: 'Last 4 weeks' },
          ]} />
          <span className="text-muted">{formatShort(start)} – {formatShort(end)}</span>
        </div>
        <p className="text-xs text-muted">Patterns in how schedules fit your days, not a judgment of effort or worth. Habit numbers are kept separate from tasks.</p>
        {data.error && <ErrorNote message={data.error} onRetry={data.reload} />}
        {data.loading && !d && <Loading />}
        {d && (
          <>
            <p>
              {d.totals.scheduled === 0 ? 'No scheduled check-ins have finished in this range yet.' :
                <>Across habits with fixed days: <strong>{d.totals.completed}</strong> of <strong>{d.totals.scheduled}</strong> scheduled check-ins completed{d.totals.pct !== null && ` (${d.totals.pct}%)`}, through {formatShort(d.evaluated_through)}.</>}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[34rem] text-left">
                <caption className="sr-only">Consistency by habit</caption>
                <thead className="text-xs text-muted">
                  <tr><th className="py-1 font-medium">Habit</th><th className="font-medium">Scheduled → done</th><th className="font-medium">Consistency</th><th className="font-medium">Weekly target</th><th className="font-medium">Paused</th><th className="font-medium">Extra</th></tr>
                </thead>
                <tbody>
                  {d.habits.map((h) => (
                    <tr key={h.habit_id} className="border-t border-line">
                      <td className="py-1.5">{h.name}{h.archived && <span className="text-muted"> (archived)</span>}</td>
                      <td>{h.scheduled_days ? `${h.scheduled_days} → ${h.completed_days}` : '—'}{h.pending_today ? <span className="text-muted"> (+ today pending)</span> : null}</td>
                      <td>{h.consistency_pct === null ? '—' : `${h.consistency_pct}%`}</td>
                      <td>{h.weekly ? (h.weekly.weeks_evaluated ? `met ${h.weekly.weeks_met} of ${h.weekly.weeks_evaluated} full weeks` : 'no full week yet') : '—'}</td>
                      <td>{h.paused_days || '—'}</td>
                      <td>{h.extra_checkins || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted">“—” means there is no data to calculate from, which is different from 0%.</p>
            <HabitReview start={start} end={end} available={d.habits.length > 0} />
          </>
        )}
      </div>
    </Disclosure>
  )
}
