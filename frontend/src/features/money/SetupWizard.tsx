import { useState } from 'react'
import { post, put } from '../../api'
import { Button, Card, ErrorNote, Field, cx, fieldBase, inputClass } from '../../components/ui'
import { useApp } from '../../context'
import { useAction } from '../../hooks'
import type { AccountType } from '../../types'
import { CURRENCIES, currencySymbol, parseAmount } from './money'

interface Draft { type: AccountType; name: string; balance: string }

function Stepper({ label, value, onChange, id }: { label: string; value: number; onChange: (n: number) => void; id: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-line bg-card px-4 py-3">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <div className="flex items-center gap-2">
        <Button size="sm" aria-label={`Fewer: ${label}`} disabled={value <= 0} onClick={() => onChange(value - 1)}>−</Button>
        <input id={id} type="number" min={0} max={10} value={value} readOnly className={cx(fieldBase, 'w-14 text-center')} />
        <Button size="sm" aria-label={`More: ${label}`} disabled={value >= 10} onClick={() => onChange(value + 1)}>+</Button>
      </div>
    </div>
  )
}

/** First-time setup: how many accounts, and what each one holds (or owes) right now. */
export function SetupWizard({ onDone }: { onDone: () => void }) {
  const { settings, reloadSettings } = useApp()
  const [step, setStep] = useState<1 | 2>(1)
  const [debits, setDebits] = useState(1)
  const [credits, setCredits] = useState(1)
  const [currency, setCurrency] = useState(settings.currency)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [swGet, setSwGet] = useState('')
  const [swPay, setSwPay] = useState('')
  const action = useAction()
  const symbol = currencySymbol(currency)

  const next = () => {
    setDrafts([
      ...Array.from({ length: debits }, (_, i) => drafts.find((d, j) => d.type === 'debit' && j === i)
        ?? { type: 'debit' as const, name: debits > 1 ? `Debit account ${i + 1}` : 'Debit account', balance: '' }),
      ...Array.from({ length: credits }, (_, i) => ({ type: 'credit' as const, name: credits > 1 ? `Credit card ${i + 1}` : 'Credit card', balance: '0' })),
    ])
    setStep(2)
  }
  const set = (i: number, patch: Partial<Draft>) => setDrafts((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)))
  const swGetCents = swGet.trim() ? parseAmount(swGet) : 0
  const swPayCents = swPay.trim() ? parseAmount(swPay) : 0
  const invalid = drafts.some((d) => !d.name.trim() || parseAmount(d.balance) === null)
    || swGetCents === null || swGetCents < 0 || swPayCents === null || swPayCents < 0
  const finish = async () => {
    const ok = await action.run(async () => {
      if (currency !== settings.currency) await put('/settings', { currency })
      const r = await post('/finance/setup', { accounts: drafts.map((d) => ({ name: d.name.trim(), type: d.type, balance_cents: parseAmount(d.balance) })) })
      if (swGetCents || swPayCents) await put('/finance/splitwise', { get_cents: swGetCents, pay_cents: swPayCents })
      return r
    })
    if (ok) { reloadSettings(); onDone() }
  }

  return (
    <Card className="mx-auto w-full max-w-xl" aria-label="Set up your accounts">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Step {step} of 2</p>
      {step === 1 ? (
        <div className="mt-2 flex flex-col gap-4">
          <div>
            <h3 className="text-lg font-semibold">Let’s set up your accounts</h3>
            <p className="text-sm text-muted">Tell us what you pay with. You can add or change accounts later.</p>
          </div>
          <Stepper id="n-debit" label="How many debit accounts do you have?" value={debits} onChange={setDebits} />
          <Stepper id="n-credit" label="How many credit cards do you have?" value={credits} onChange={setCredits} />
          <Field label="Currency" htmlFor="money-currency">
            <select id="money-currency" className={cx(fieldBase, 'w-32')} value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <div className="flex justify-end">
            <Button variant="primary" disabled={debits + credits === 0} onClick={next}>Next</Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex flex-col gap-4">
          <div>
            <h3 className="text-lg font-semibold">What’s in them right now?</h3>
            <p className="text-sm text-muted">For a debit account, enter the money in it. For a credit card, enter what you owe today (0 if nothing).</p>
          </div>
          {drafts.map((d, i) => (
            <fieldset key={i} className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-[1fr_11rem]">
              <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted">{d.type === 'debit' ? 'Debit account' : 'Credit card'}</legend>
              <Field label="Name" htmlFor={`acc-name-${i}`}>
                <input id={`acc-name-${i}`} className={inputClass} value={d.name} maxLength={60} onChange={(e) => set(i, { name: e.target.value })} />
              </Field>
              <Field label={d.type === 'debit' ? 'Current balance' : 'Amount owed now'} htmlFor={`acc-bal-${i}`}>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm text-muted">{symbol}</span>
                  <input id={`acc-bal-${i}`} inputMode="decimal" className={inputClass} placeholder="0.00" value={d.balance}
                    aria-invalid={d.balance !== '' && parseAmount(d.balance) === null} onChange={(e) => set(i, { balance: e.target.value })} />
                </div>
              </Field>
            </fieldset>
          ))}
          <fieldset className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-2">
            <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted">Splitwise (optional)</legend>
            {([['You should get', swGet, setSwGet, 'sw-get'], ['You should pay', swPay, setSwPay, 'sw-pay']] as const).map(([label, value, onChange, id]) => (
              <Field key={id} label={label} htmlFor={id}>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm text-muted">{symbol}</span>
                  <input id={id} inputMode="decimal" className={inputClass} placeholder="0.00" value={value}
                    aria-invalid={value.trim() !== '' && (parseAmount(value) ?? -1) < 0} onChange={(e) => onChange(e.target.value)} />
                </div>
              </Field>
            ))}
            <p className="text-xs text-muted sm:col-span-2">Copy the totals from your Splitwise app. Leave blank if you don’t use it.</p>
          </fieldset>
          {action.error && <ErrorNote message={action.error} />}
          <div className="flex justify-between">
            <Button onClick={() => setStep(1)}>Back</Button>
            <Button variant="primary" pending={action.pending} disabled={invalid} onClick={finish}>Start tracking</Button>
          </div>
        </div>
      )}
    </Card>
  )
}
