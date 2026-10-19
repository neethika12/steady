import { Button, inputClass } from '../../components/ui'

export interface StepDraft { title: string; estimated_minutes: string; planned_date: string }

export const emptyStep = (): StepDraft => ({ title: '', estimated_minutes: '', planned_date: '' })

export function stepsPayload(steps: StepDraft[]) {
  return steps.filter((s) => s.title.trim()).map((s) => ({
    title: s.title.trim(),
    estimated_minutes: s.estimated_minutes ? Math.max(1, Math.round(Number(s.estimated_minutes))) : null,
    planned_date: s.planned_date || null,
  }))
}

/** Editable list of smaller tasks. Dates are optional: nothing is scheduled unless you choose. */
export function SplitEditor({ steps, onChange }: { steps: StepDraft[]; onChange: (s: StepDraft[]) => void }) {
  const set = (i: number, patch: Partial<StepDraft>) => onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  return (
    <div className="flex flex-col gap-2">
      {steps.map((s, i) => (
        <fieldset key={i} className="grid gap-2 rounded-lg border border-line p-2 sm:grid-cols-[1fr_6rem_9.5rem_auto]">
          <legend className="sr-only">Step {i + 1}</legend>
          <input aria-label={`Step ${i + 1} title`} className={inputClass} placeholder={`Step ${i + 1}`} value={s.title} maxLength={200}
            onChange={(e) => set(i, { title: e.target.value })} />
          <input aria-label={`Step ${i + 1} minutes`} type="number" min={1} className={inputClass} placeholder="min" value={s.estimated_minutes}
            onChange={(e) => set(i, { estimated_minutes: e.target.value })} />
          <input aria-label={`Step ${i + 1} date (optional)`} type="date" className={inputClass} value={s.planned_date}
            onChange={(e) => set(i, { planned_date: e.target.value })} />
          <Button size="sm" variant="ghost" aria-label={`Remove step ${i + 1}`} disabled={steps.length === 1}
            onClick={() => onChange(steps.filter((_, j) => j !== i))}>Remove</Button>
        </fieldset>
      ))}
      <div><Button size="sm" onClick={() => onChange([...steps, emptyStep()])} disabled={steps.length >= 20}>+ Add step</Button></div>
    </div>
  )
}
