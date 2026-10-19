import { useState } from 'react'
import { put } from '../api'
import { useApp } from '../context'
import { formatTime, timelineSpan } from '../dates'
import { notifyChanged, useAction } from '../hooks'
import { Button, Dialog, ErrorNote, cx, fieldBase, useToast } from './ui'

const PRESETS = [
  { label: 'Early bird', start: '06:00', end: '21:00' },
  { label: 'Standard', start: '08:00', end: '22:00' },
  { label: 'Night owl', start: '11:00', end: '02:00' },
]

export function describeTimeline(s: { timeline_start: string; timeline_end: string }) {
  return `${formatTime(s.timeline_start)} – ${formatTime(s.timeline_end)}`
}

/** Choose the hours your Day timeline shows. An end before the start runs past midnight. */
export function TimelineHoursForm({ onSaved }: { onSaved?: () => void }) {
  const { settings, reloadSettings } = useApp()
  const [start, setStart] = useState(settings.timeline_start.slice(0, 5))
  const [end, setEnd] = useState(settings.timeline_end.slice(0, 5))
  const action = useAction()
  const toast = useToast()
  const span = timelineSpan({ timeline_start: start || '00:00', timeline_end: end || '00:00' })
  const same = start === end
  const save = async () => {
    if (await action.run(() => put('/settings', { timeline_start: start, timeline_end: end }))) {
      toast('Timeline hours saved')
      reloadSettings()
      notifyChanged('tasks', 'habits', 'journal')
      onSaved?.()
    }
  }
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div role="group" aria-label="Presets" className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <Button key={p.label} size="sm" variant={start === p.start && end === p.end ? 'primary' : 'secondary'}
            aria-pressed={start === p.start && end === p.end} onClick={() => { setStart(p.start); setEnd(p.end) }}>
            {p.label} <span className={cx('text-xs', start === p.start && end === p.end ? 'text-white/80' : 'text-muted')}>{formatTime(p.start)}–{formatTime(p.end)}</span>
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="tl-start">My day starts at</label>
        <input id="tl-start" type="time" step={1800} className={`${fieldBase} py-1.5`} value={start} onChange={(e) => setStart(e.target.value)} />
        <label htmlFor="tl-end">and ends at</label>
        <input id="tl-end" type="time" step={1800} className={`${fieldBase} py-1.5`} value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      {same ? <p className="text-xs text-danger">Start and end must be different.</p> : span.pastMidnight ? (
        <p className="rounded-lg bg-accent-soft px-3 py-2 text-xs text-ink">
          Your day runs past midnight. Until <strong>{formatTime(end)}</strong> it still counts as the previous day,
          so late-night tasks, habits and journal entries stay with the day you’re living.
        </p>
      ) : <p className="text-xs text-muted">The timeline shows {formatTime(start)} to {formatTime(end)}. Your day changes at midnight.</p>}
      <div><Button variant="primary" size="sm" pending={action.pending} disabled={same || !start || !end} onClick={save}>Save hours</Button></div>
      {action.error && <ErrorNote message={action.error} />}
    </div>
  )
}

export function TimelineHoursDialog({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Timeline hours" onClose={onClose}>
      <TimelineHoursForm onSaved={onClose} />
    </Dialog>
  )
}

export function useTimeline() {
  const { settings } = useApp()
  return timelineSpan(settings)
}
