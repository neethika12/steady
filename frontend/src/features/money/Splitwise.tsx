import { useState } from 'react'
import { put } from '../../api'
import { Button, Dialog, ErrorNote, Field, inputClass } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import type { MoneySplitwise } from '../../types'
import { currencySymbol, formatMoney, parseAmount } from './money'

/** Splitwise, shown beside your accounts: the two totals from the Splitwise app, updated by hand. */
export function SplitwiseCard({ data }: { data: MoneySplitwise }) {
  const { settings } = useApp()
  const cur = settings.currency
  const [editing, setEditing] = useState(false)
  return (
    <div aria-label="Splitwise" role="group" className="min-w-52 flex-1 rounded-xl border border-line bg-card px-4 py-3 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div className="flex items-center gap-2">
        <p className="flex items-center gap-2 text-xs font-medium text-muted">
          <span aria-hidden className="size-2 rounded-full bg-accent" />
          Splitwise
        </p>
        <Button size="xs" variant="ghost" className="ml-auto -my-1" onClick={() => setEditing(true)}>Update</Button>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-muted">You should get</p>
          <p className="text-lg font-semibold tabular-nums text-teal">{formatMoney(data.get_cents, cur)}</p>
        </div>
        <div>
          <p className="text-xs text-muted">You should pay</p>
          <p className="text-lg font-semibold tabular-nums text-danger">{formatMoney(data.pay_cents, cur)}</p>
        </div>
      </div>
      {data.updated_at && <p className="text-xs text-muted">Updated {formatShort(data.updated_at.slice(0, 10))}</p>}
      {editing && <SplitwiseDialog data={data} onClose={() => setEditing(false)} />}
    </div>
  )
}

function SplitwiseDialog({ data, onClose }: { data: MoneySplitwise; onClose: () => void }) {
  const { settings } = useApp()
  const symbol = currencySymbol(settings.currency)
  const [get, setGet] = useState((data.get_cents / 100).toFixed(2))
  const [pay, setPay] = useState((data.pay_cents / 100).toFixed(2))
  const action = useAction()
  const getCents = get.trim() ? parseAmount(get) : 0
  const payCents = pay.trim() ? parseAmount(pay) : 0
  const bad = getCents === null || getCents < 0 || payCents === null || payCents < 0
  const save = async () => {
    if (bad) return
    if (await action.run(() => put('/finance/splitwise', { get_cents: getCents, pay_cents: payCents }))) {
      notifyChanged('money'); onClose()
    }
  }
  const field = (id: string, label: string, value: string, onChange: (v: string) => void) => (
    <Field label={label} htmlFor={id}>
      <div className="flex items-center gap-1.5">
        <span className="text-sm text-muted">{symbol}</span>
        <input id={id} inputMode="decimal" className={inputClass} placeholder="0.00" value={value}
          aria-invalid={value.trim() !== '' && (parseAmount(value) ?? -1) < 0} onChange={(e) => onChange(e.target.value)} />
      </div>
    </Field>
  )
  return (
    <Dialog title="Update Splitwise" onClose={onClose}>
      <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); save() }}>
        <p className="text-sm text-muted">Copy the totals from your Splitwise app.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {field('sw-get-edit', 'You should get', get, setGet)}
          {field('sw-pay-edit', 'You should pay', pay, setPay)}
        </div>
        {bad && <p role="alert" className="text-sm text-danger">Enter amounts of zero or more.</p>}
        {action.error && <ErrorNote message={action.error} />}
        <div><Button type="submit" variant="primary" pending={action.pending} disabled={bad}>Save</Button></div>
      </form>
    </Dialog>
  )
}
