import { useState } from 'react'
import { get } from '../../api'
import { Disclosure, ErrorNote, Loading, Segmented } from '../../components/ui'
import { useApp } from '../../context'
import { addDays, formatMinutes, formatShort, weekStart } from '../../dates'
import { useLoad, useOnChanged } from '../../hooks'
import type { TaskInsights as Insights } from '../../types'
import { ReasonsSummary } from '../ai/ReasonsSummary'
import { CALCULATION_NOTE } from './DayStatsSummary'

export function TaskInsights() {
  const { date, settings } = useApp()
  const [range, setRange] = useState<'week' | 'four'>('week')
  const end = addDays(weekStart(date, settings.week_start), 6)
  const start = range === 'week' ? weekStart(date, settings.week_start) : addDays(end, -27)
  const data = useLoad<Insights>((s) => get(`/insights/tasks?start=${start}&end=${end}`, s), `ti-${start}-${end}`)
  useOnChanged(['tasks'], data.reload)
  const d = data.data

  return (
    <Disclosure title="Planning insights">
      <div className="flex flex-col gap-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Insight range" size="sm" value={range} onChange={setRange} options={[
            { value: 'week', label: 'This week' }, { value: 'four', label: 'Last 4 weeks' },
          ]} />
          <span className="text-muted">{formatShort(start)} – {formatShort(end)}</span>
        </div>
        <p className="text-xs text-muted">
          These describe how plans and days went: useful for adjusting plans, not a measure of you.
        </p>
        {data.error && <ErrorNote message={data.error} onRetry={data.reload} />}
        {data.loading && !d && <Loading />}
        {d && (
          <>
            <section>
              <h4 className="font-semibold">Completion</h4>
              {d.totals.counted === 0 ? <p className="text-muted">No tasks were planned in this range (through {formatShort(d.evaluated_through)}).</p> : (
                <p>
                  {d.totals.completed} of {d.totals.counted} planned tasks completed
                  {d.totals.completion_pct !== null && <> (<strong>{d.totals.completion_pct}%</strong>)</>}
                  {' '}through {formatShort(d.evaluated_through)}.
                  {!!d.totals.partial && ` ${d.totals.partial} partly completed.`}
                  {!!d.totals.not_completed && ` ${d.totals.not_completed} not completed.`}
                  {!!d.totals.awaiting_review && ` ${d.totals.awaiting_review} not marked yet (no outcome recorded).`}
                  {!!d.totals.cancelled && ` ${d.totals.cancelled} cancelled and not counted.`}
                </p>
              )}
              <p className="mt-1 text-xs text-muted">{CALCULATION_NOTE}</p>
            </section>

            <section>
              <h4 className="font-semibold">What got in the way</h4>
              {d.reasons.unfinished === 0 ? <p className="text-muted">No tasks were reviewed as unfinished in this range.</p> : (
                <>
                  <p>{d.reasons.with_reason} of {d.reasons.unfinished} unfinished task{d.reasons.unfinished === 1 ? '' : 's'} have a written reason.</p>
                  {d.reasons.by_reason.length > 0 && (
                    <ul className="mt-1 list-inside list-disc">
                      {d.reasons.by_reason.map((r) => (
                        <li key={r.reason}>Of {d.reasons.tagged} tagged reason{d.reasons.tagged === 1 ? '' : 's'}, {r.count} {r.count === 1 ? 'was' : 'were'} “{r.label}”.</li>
                      ))}
                    </ul>
                  )}
                  {d.reasons.untagged > 0 && <p className="mt-1 text-muted">{d.reasons.untagged} reason{d.reasons.untagged === 1 ? ' has' : 's have'} no tag; the AI summary can read the written text.</p>}
                  {d.reasons.records.length > 0 && (
                    <details className="mt-1"><summary className="cursor-pointer text-muted">Show written reasons</summary>
                      <ul className="mt-1 list-inside list-disc text-muted">
                        {d.reasons.records.slice(0, 20).map((r) => <li key={r.plan_id}>{formatShort(r.date)} · {r.task_title}: {r.note || r.reason}</li>)}
                      </ul>
                    </details>
                  )}
                  {d.reasons.without_reason > 0 && <p className="mt-1 text-muted">{d.reasons.without_reason} older unfinished task{d.reasons.without_reason === 1 ? ' has' : 's have'} no reason recorded.</p>}
                  <div className="mt-2"><ReasonsSummary start={start} end={end} available={d.reasons.with_reason > 0} /></div>
                </>
              )}
            </section>

            <section>
              <h4 className="font-semibold">Carried forward</h4>
              {d.carryover.carried_plans === 0 ? <p className="text-muted">No tasks were carried forward from an earlier day.</p> : (
                <>
                  <p>{d.carryover.carried_plans} planned task{d.carryover.carried_plans === 1 ? ' was' : 's were'} carried over from an earlier day ({d.carryover.tasks_carried} distinct task{d.carryover.tasks_carried === 1 ? '' : 's'}; {d.carryover.share_of_plans_pct}% of plans in this range).</p>
                  <ul className="mt-1 list-inside list-disc text-muted">
                    {d.carryover.most_carried.map((t) => <li key={t.task_id}>{t.title}: carried {t.times_carried}×</li>)}
                  </ul>
                </>
              )}
            </section>

            <section>
              <h4 className="font-semibold">Estimated vs actual time</h4>
              {d.durations.tasks_with_both === 0 ? (
                <p className="text-muted">No completed tasks have both an estimate and an actual duration yet. Add “actual minutes” when editing a task to see this.</p>
              ) : (
                <>
                  <p>For {d.durations.tasks_with_both} completed task{d.durations.tasks_with_both === 1 ? '' : 's'} with both numbers: estimated {formatMinutes(d.durations.estimated_total)}, actual {formatMinutes(d.durations.actual_total)}.</p>
                  <table className="mt-2 w-full text-left text-xs">
                    <thead><tr className="text-muted"><th className="py-1 font-medium">Task</th><th className="font-medium">Estimated</th><th className="font-medium">Actual</th></tr></thead>
                    <tbody>{d.durations.rows.map((r) => (
                      <tr key={r.task_id} className="border-t border-line"><td className="py-1">{r.title}</td><td>{formatMinutes(r.estimated_minutes)}</td><td>{formatMinutes(r.actual_minutes)}</td></tr>
                    ))}</tbody>
                  </table>
                  {d.durations.completed_without_actual > 0 && <p className="mt-1 text-xs text-muted">{d.durations.completed_without_actual} completed task(s) are missing one of the two numbers.</p>}
                </>
              )}
            </section>
          </>
        )}
      </div>
    </Disclosure>
  )
}
