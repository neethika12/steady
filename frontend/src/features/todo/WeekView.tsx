import { ErrorNote, cx } from '../../components/ui'
import { useApp } from '../../context'
import { formatDayMonth, formatShort, formatWeekday } from '../../dates'
import type { Week } from '../../types'
import { useDropToDay } from './dropToDay'
import { PlanRow } from './PlanRow'

export function WeekView({ week, onChanged, onOpenDay }: { week: Week; onChanged: () => void; onOpenDay: (d: string) => void }) {
  const { over, error, bind } = useDropToDay(onChanged)
  const { today, date } = useApp()

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p className="text-sm text-muted">
        Drag tasks from the Inbox (or another day) onto a day, or use <strong>Move to date</strong>.
      </p>
      {error && <ErrorNote message={error} />}
      <ol className="grid gap-2 sm:grid-cols-2 md:grid-cols-4 xl:grid-cols-7" aria-label="Week">
        {week.days.map((d) => (
          <li
            key={d.date}
            {...bind(d.date)}
            className={cx('flex min-h-40 flex-col gap-2 rounded-xl border bg-card p-2 transition-colors',
              over === d.date ? 'border-accent bg-accent-soft' : 'border-line',
              d.date === date && 'ring-2 ring-accent/40')}
          >
            <button type="button" onClick={() => onOpenDay(d.date)} className="rounded-md px-1 text-left hover:bg-paper"
              aria-label={`Open ${formatWeekday(d.date)} ${formatShort(d.date)} in day view`}>
              <span className={cx('block text-xs font-semibold uppercase tracking-wide', d.date === today ? 'text-accent' : 'text-muted')}>
                {formatWeekday(d.date)}{d.date === today && ' · today'}
              </span>
              <span className="block text-sm font-medium">{formatDayMonth(d.date)}</span>
              <span className="block text-xs text-muted">
                {d.stats.planned === 0 ? 'No tasks planned.'
                  : `${d.stats.completed}/${d.stats.counted} done${d.stats.completion_pct !== null ? ` · ${d.stats.completion_pct}%` : ''}`}
              </span>
            </button>
            <ul className="flex flex-col gap-1.5">
              {d.plans.map((p) => <PlanRow key={p.id} plan={p} compact onChanged={onChanged} />)}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  )
}
