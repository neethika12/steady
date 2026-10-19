import { useState } from 'react'
import { useApp } from '../context'
import { addDays, formatShort, relativeLabel, timelineSpan, weekDays } from '../dates'
import { Button, Dialog, ErrorNote, Field, Segmented, fieldBase, inputClass } from './ui'

export interface TimeValue { mode: 'anytime' | 'at' | 'range'; start: string; end: string }

export function initialTime(start?: string | null, end?: string | null): TimeValue {
  return { mode: !start ? 'anytime' : end ? 'range' : 'at', start: start?.slice(0, 5) ?? '09:00', end: end?.slice(0, 5) ?? '10:00' }
}

/** What the API expects: { planned_time, planned_end_time }. */
export function timePayload(v: TimeValue) {
  if (v.mode === 'anytime') return { planned_time: null, planned_end_time: null }
  if (v.mode === 'at') return { planned_time: v.start, planned_end_time: null }
  return { planned_time: v.start, planned_end_time: v.end }
}

/** `pastMidnightOk`: the user's timeline runs past midnight, so 23:30–00:30 is a valid range. */
export function timeError(v: TimeValue, pastMidnightOk = false): string | null {
  if (v.mode === 'anytime') return null
  if (!v.start) return 'Choose a start time.'
  if (v.mode !== 'range') return null
  if (!v.end || v.end === v.start) return 'The end time must be after the start time.'
  if (v.end < v.start && !pastMidnightOk) return 'The end time must be after the start time.'
  return null
}

/** Pick a day and a time (anytime, a start time, or a from–to range): the keyboard/touch alternative to dragging. */
export function MoveToDateDialog({ title, description, initialDate, initialStart = null, initialEnd = null, confirmLabel = 'Move', onConfirm, onClose, pending, error }: {
  title: string
  description?: string
  initialDate?: string
  initialStart?: string | null
  initialEnd?: string | null
  confirmLabel?: string
  onConfirm: (date: string, times: { planned_time: string | null; planned_end_time: string | null }) => void
  onClose: () => void
  pending?: boolean
  error?: string | null
}) {
  const { today, date: selected, settings } = useApp()
  const [value, setValue] = useState(initialDate ?? selected)
  const [time, setTime] = useState<TimeValue>(initialTime(initialStart, initialEnd))
  const quick = Array.from(new Set([today, addDays(today, 1), ...weekDays(selected, settings.week_start)]))
  const pastMidnightOk = timelineSpan(settings).pastMidnight
  return (
    <Dialog title={title} onClose={onClose} footer={<>
      <Button onClick={onClose}>Cancel</Button>
      <Button variant="primary" pending={pending} disabled={!value || !!timeError(time, pastMidnightOk)}
        onClick={() => onConfirm(value, timePayload(time))}>{confirmLabel}</Button>
    </>}>
      <div className="flex flex-col gap-4">
        {description && <p className="text-sm text-muted">{description}</p>}
        <div role="group" aria-label="Quick dates" className="flex flex-wrap gap-2">
          {quick.map((d) => (
            <Button key={d} size="sm" variant={d === value ? 'primary' : 'secondary'} aria-pressed={d === value} onClick={() => setValue(d)}>
              {relativeLabel(d, today) === formatShort(d) ? formatShort(d) : `${relativeLabel(d, today)} · ${formatShort(d)}`}
            </Button>
          ))}
        </div>
        <Field label="Or pick a date" htmlFor="move-date">
          <input id="move-date" type="date" className={inputClass} value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
        <TimeChoice value={time} onChange={setTime} idPrefix="move" />
        {error && <ErrorNote message={error} />}
      </div>
    </Dialog>
  )
}

/** Anytime, a start time, or a from–to range on that day. */
export function TimeChoice({ value, onChange, idPrefix }: { value: TimeValue; onChange: (v: TimeValue) => void; idPrefix: string }) {
  const { settings } = useApp()
  const pastMidnightOk = timelineSpan(settings).pastMidnight
  const err = timeError(value, pastMidnightOk)
  const overnight = value.mode === 'range' && !err && value.end < value.start
  return (
    <Field label="Time">
      <div className="flex flex-col gap-2">
        <Segmented label="Time of day" value={value.mode} onChange={(mode) => onChange({ ...value, mode })} options={[
          { value: 'anytime', label: 'Anytime' }, { value: 'at', label: 'At a time' }, { value: 'range', label: 'From – to' },
        ]} />
        {value.mode !== 'anytime' && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label htmlFor={`${idPrefix}-start`} className={value.mode === 'range' ? '' : 'sr-only'}>From</label>
            <input id={`${idPrefix}-start`} type="time" aria-label={value.mode === 'range' ? 'Start time' : 'Time'}
              className={`${fieldBase} py-1.5`} value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />
            {value.mode === 'range' && <>
              <label htmlFor={`${idPrefix}-end`}>to</label>
              <input id={`${idPrefix}-end`} type="time" aria-label="End time" aria-invalid={!!err}
                className={`${fieldBase} py-1.5`} value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} />
            </>}
          </div>
        )}
        {err && <p role="alert" className="text-xs text-danger">{err}</p>}
        {overnight && <p className="text-xs text-muted">Runs past midnight, into the late part of your day.</p>}
      </div>
    </Field>
  )
}
