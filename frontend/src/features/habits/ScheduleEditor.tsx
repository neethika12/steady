import { Field, Segmented, cx, fieldBase } from '../../components/ui'
import { WEEKDAY_NAMES, WEEKDAY_SHORT } from '../../dates'
import type { HabitKind, ScheduleInput } from '../../types'

export const defaultSchedule: ScheduleInput = { schedule_type: 'daily', weekdays: [], weekly_target: null, target_value: 1 }

export function KindPicker({ kind, onChange }: { kind: HabitKind; onChange: (k: HabitKind) => void }) {
  return (
    <Field label="How is it measured?">
      <Segmented label="Habit type" value={kind} onChange={onChange} options={[
        { value: 'boolean', label: 'Yes / no' },
        { value: 'duration', label: 'Minutes' },
        { value: 'count', label: 'Count' },
      ]} />
    </Field>
  )
}

export function ScheduleEditor({ value, onChange, kind, unit, idPrefix }: {
  value: ScheduleInput; onChange: (v: ScheduleInput) => void; kind: HabitKind; unit?: string | null; idPrefix: string
}) {
  const set = (patch: Partial<ScheduleInput>) => onChange({ ...value, ...patch })
  const toggleDay = (d: number) =>
    set({ weekdays: value.weekdays.includes(d) ? value.weekdays.filter((x) => x !== d) : [...value.weekdays, d].sort() })
  return (
    <div className="flex flex-col gap-4">
      <Field label="Schedule">
        <Segmented label="Schedule type" value={value.schedule_type} onChange={(t) => set({
          schedule_type: t,
          weekly_target: t === 'weekly_target' ? (value.weekly_target ?? 3) : null,
          weekdays: t === 'weekdays' ? (value.weekdays.length ? value.weekdays : [0, 2, 4]) : [],
        })} options={[
          { value: 'daily', label: 'Every day' },
          { value: 'weekdays', label: 'Chosen weekdays' },
          { value: 'weekly_target', label: 'Times per week' },
        ]} />
      </Field>
      {value.schedule_type === 'weekdays' && (
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Which days?</legend>
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAY_SHORT.map((d, i) => (
              <label key={d} className={cx('cursor-pointer rounded-lg border px-2.5 py-1.5 text-sm',
                value.weekdays.includes(i) ? 'border-accent bg-accent-soft text-accent' : 'border-line')}>
                <input type="checkbox" className="sr-only" checked={value.weekdays.includes(i)} onChange={() => toggleDay(i)}
                  aria-label={WEEKDAY_NAMES[i]} />
                {d}
              </label>
            ))}
          </div>
          {value.weekdays.length === 0 && <p className="mt-1 text-xs text-danger">Choose at least one day.</p>}
        </fieldset>
      )}
      {value.schedule_type === 'weekly_target' && (
        <Field label="Sessions per week" htmlFor={`${idPrefix}-weekly`} hint="Any days count. Progress is judged per week, never as daily misses.">
          <input id={`${idPrefix}-weekly`} type="number" min={1} max={7} className={`${fieldBase} w-24`}
            value={value.weekly_target ?? 3} onChange={(e) => set({ weekly_target: Math.min(7, Math.max(1, Number(e.target.value) || 1)) })} />
        </Field>
      )}
      {kind !== 'boolean' && (
        <Field label={kind === 'duration' ? 'Minutes per day to count as done' : `Target per day${unit ? ` (${unit})` : ''}`} htmlFor={`${idPrefix}-target`}>
          <input id={`${idPrefix}-target`} type="number" min={1} max={1440} className={`${fieldBase} w-28`}
            value={value.target_value} onChange={(e) => set({ target_value: Math.max(1, Number(e.target.value) || 1) })} />
        </Field>
      )}
    </div>
  )
}

export function scheduleIsValid(s: ScheduleInput): boolean {
  if (s.schedule_type === 'weekdays') return s.weekdays.length > 0
  if (s.schedule_type === 'weekly_target') return !!s.weekly_target
  return true
}

export function describeSchedule(s: ScheduleInput | null, kind: HabitKind, unit: string | null): string {
  if (!s) return 'No schedule'
  const when = s.schedule_type === 'daily' ? 'Every day'
    : s.schedule_type === 'weekdays' ? s.weekdays.map((d) => WEEKDAY_SHORT[d]).join(', ')
    : `${s.weekly_target}× per week`
  const amount = kind === 'duration' ? ` · ${s.target_value} min` : kind === 'count' ? ` · ${s.target_value}${unit ? ` ${unit}` : ''}` : ''
  return when + amount
}
