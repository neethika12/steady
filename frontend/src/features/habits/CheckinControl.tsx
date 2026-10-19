import { useEffect, useState } from 'react'
import { del, put } from '../../api'
import { habitMessage } from '../../components/Motivation'
import { Button, ErrorNote, cx, fieldBase, useToast } from '../../components/ui'
import { notifyChanged, useAction } from '../../hooks'
import type { HabitDayItem } from '../../types'

/** Record a check-in. Values are absolute (not "+1" requests), so repeats can't double-count. */
export function CheckinControl({ item, date, disabled, onChanged }: {
  item: HabitDayItem; date: string; disabled: boolean; onChanged: () => void
}) {
  const { habit } = item
  const target = item.target_value ?? 1
  const [value, setValue] = useState(item.value ?? 0)
  const action = useAction()
  const toast = useToast()
  useEffect(() => setValue(item.value ?? 0), [item.value])

  const save = async (v: number | null) => {
    const r = await action.run(() => v === null
      ? del(`/habits/${habit.id}/checkins/${date}`).then(() => true)
      : put(`/habits/${habit.id}/checkins/${date}`, { value: v }))
    if (r !== undefined) {
      if (v !== null && v >= target) toast(habitMessage())
      notifyChanged('habits'); onChanged()
    } else setValue(item.value ?? 0)
  }

  if (habit.kind === 'boolean') {
    const done = (item.value ?? 0) >= 1
    return (
      <div>
        <Button size="sm" variant={done ? 'primary' : 'secondary'} aria-pressed={done} disabled={disabled} pending={action.pending}
          onClick={() => save(done ? null : 1)} aria-label={`${habit.name}: ${done ? 'done, press to undo' : 'mark done'}`}>
          {done ? '✓ Done' : 'Mark done'}
        </Button>
        {action.error && <div className="mt-1"><ErrorNote message={action.error} /></div>}
      </div>
    )
  }

  const unit = habit.kind === 'duration' ? 'min' : habit.unit ?? ''
  const step = habit.kind === 'duration' ? 5 : 1
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1">
        <Button size="sm" disabled={disabled || value <= 0} pending={action.pending} aria-label={`Decrease ${habit.name}`}
          onClick={() => { const v = Math.max(0, value - step); setValue(v); save(v) }}>−</Button>
        <label className="sr-only" htmlFor={`ci-${habit.id}`}>{habit.name} ({unit})</label>
        <input id={`ci-${habit.id}`} type="number" min={0} inputMode="numeric" disabled={disabled}
          className={cx(fieldBase, 'w-20 text-center')} value={value}
          onChange={(e) => setValue(Math.max(0, Number(e.target.value) || 0))}
          onBlur={() => { if (value !== (item.value ?? 0)) save(value) }}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }} />
        <Button size="sm" disabled={disabled} pending={action.pending} aria-label={`Increase ${habit.name}`}
          onClick={() => { const v = value + step; setValue(v); save(v) }}>+</Button>
      </div>
      <span className="text-xs text-muted">{item.value ?? 0} / {target} {unit}</span>
      {action.error && <ErrorNote message={action.error} />}
    </div>
  )
}
