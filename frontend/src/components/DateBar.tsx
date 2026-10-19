import { useApp } from '../context'
import { addDays, formatLong, relativeLabel } from '../dates'
import { Button, fieldBase } from './ui'

/** Prev / Today / Yesterday / Next and a calendar picker. `step` is 1 (days) or 7 (weeks). */
export function DateControls({ step = 1 }: { step?: 1 | 7 }) {
  const { date, setDate, today } = useApp()
  const yesterday = addDays(today, -1)
  const unit = step === 7 ? 'week' : 'day'
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Choose day">
      <Button size="sm" onClick={() => setDate(addDays(date, -step))} aria-label={`Previous ${unit}`}>‹</Button>
      <Button size="sm" variant={date === today ? 'primary' : 'secondary'} onClick={() => setDate(today)} aria-pressed={date === today}>Today</Button>
      <Button size="sm" variant={date === yesterday ? 'primary' : 'secondary'} onClick={() => setDate(yesterday)} aria-pressed={date === yesterday}>Yesterday</Button>
      <Button size="sm" onClick={() => setDate(addDays(date, step))} aria-label={`Next ${unit}`}>›</Button>
      <label className="sr-only" htmlFor="shared-date">Pick a date</label>
      <input
        id="shared-date"
        type="date"
        value={date}
        onChange={(e) => e.target.value && setDate(e.target.value)}
        className={`${fieldBase} py-1`}
      />
    </div>
  )
}

/** Date heading plus controls, used by the Habit Tracker and Journal tabs. */
export function DateBar() {
  const { date, today } = useApp()
  const rel = relativeLabel(date, today)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="w-full min-w-0 sm:mr-auto sm:w-auto">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          {rel === 'Today' || rel === 'Yesterday' || rel === 'Tomorrow' ? rel : 'Selected day'}
        </p>
        <h2 className="truncate text-lg font-semibold" aria-live="polite">{formatLong(date)}</h2>
      </div>
      <DateControls />
    </div>
  )
}
