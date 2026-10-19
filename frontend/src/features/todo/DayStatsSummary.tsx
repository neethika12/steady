import { ProgressRing, progressMessage } from '../../components/Motivation'
import { Badge } from '../../components/ui'
import { formatMinutes } from '../../dates'
import type { DayStats } from '../../types'
import { CANCEL_EXPLANATION } from './labels'

export function DayStatsSummary({ stats, isPast, isToday = false }: { stats: DayStats; isPast: boolean; isToday?: boolean }) {
  const when = isToday ? 'today' : isPast ? 'past' : 'future'
  if (stats.planned === 0) {
    return (
      <div className="flex items-center gap-4">
        <ProgressRing pct={null} />
        <div>
          <p className="font-semibold">No tasks planned.</p>
          <p className="text-sm text-muted">{progressMessage(null, 0, when)}</p>
        </div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <ProgressRing pct={stats.completion_pct} />
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold">{progressMessage(stats.completion_pct, stats.counted, when)}</p>
          <p className="text-sm text-muted">
            <strong className="text-ink">{stats.completed}</strong> of <strong className="text-ink">{stats.counted}</strong> planned task{stats.counted === 1 ? '' : 's'} completed
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {stats.partial > 0 && <Badge tone="warn">{stats.partial} partly completed</Badge>}
        {stats.not_completed > 0 && <Badge tone="danger">{stats.not_completed} not completed</Badge>}
        {stats.awaiting_review > 0 && <Badge tone="warn">{stats.awaiting_review} not marked yet</Badge>}
        {stats.open > 0 && <Badge>{stats.open} still open</Badge>}
        {stats.carried_in > 0 && <Badge tone="accent">{stats.carried_in} carried forward</Badge>}
        {stats.cancelled > 0 && <Badge title={CANCEL_EXPLANATION}>{stats.cancelled} cancelled · not counted</Badge>}
      </div>
      {stats.estimated_minutes_planned > 0 && (
        <p className="text-xs text-muted">
          Planned effort: {formatMinutes(stats.estimated_minutes_completed)} of {formatMinutes(stats.estimated_minutes_planned)} estimated
          {stats.effort_pct !== null && ` (${stats.effort_pct}%)`}
          {stats.plans_without_estimate > 0 && ` · ${stats.plans_without_estimate} without an estimate`}
        </p>
      )}
      {isPast && stats.awaiting_review > 0 && (
        <p className="text-xs text-muted">Tasks not marked yet still count in this day’s total until you mark them completed or not completed.</p>
      )}
    </div>
  )
}

export const CALCULATION_NOTE =
  'Completion % = completed ÷ (planned − cancelled), rounded to the nearest whole number. Not completed and not-yet-marked tasks stay in the total. Each day keeps its own record, so a task carried forward counts on every day it was planned.'
