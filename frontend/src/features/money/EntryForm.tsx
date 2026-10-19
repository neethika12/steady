import { useState } from 'react'
import { newId, patch, post } from '../../api'
import { Button, ErrorNote, Segmented, cx, inputClass } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import type { MoneyAccount, MoneyCategory, MoneyEntry, MoneyKind } from '../../types'
import { currencySymbol, parseAmount } from './money'

export const KINDS: { value: MoneyKind; label: string }[] = [
  { value: 'expense', label: 'Spent' },
  { value: 'income', label: 'Money in' },
  { value: 'payment', label: 'Card payment' },
]

/** Add (or edit) one money entry for the selected day. */
export function EntryForm({ date, accounts, categories, entry, onSaved }: {
  date: string; accounts: MoneyAccount[]; categories: MoneyCategory[]; entry?: MoneyEntry; onSaved?: () => void
}) {
  const { settings } = useApp()
  const debit = accounts.filter((a) => a.type === 'debit')
  const credit = accounts.filter((a) => a.type === 'credit')
  const [id, setId] = useState(newId)
  const [kind, setKind] = useState<MoneyKind>(entry?.kind ?? 'expense')
  const [amount, setAmount] = useState(entry ? (entry.amount_cents / 100).toFixed(2) : '')
  const [categoryId, setCategoryId] = useState<string | null>(entry?.category_id ?? null)
  const [note, setNote] = useState(entry?.note ?? '')
  const [accountId, setAccountId] = useState<string | null>(entry?.account_id ?? (accounts[0]?.id ?? null))
  const [toAccountId, setToAccountId] = useState<string | null>(entry?.to_account_id ?? (credit[0]?.id ?? null))
  const [tried, setTried] = useState(false)
  const action = useAction()

  const cats = categories.filter((c) => c.kind === (kind === 'income' ? 'income' : 'expense') && !c.archived)
  const category = cats.some((c) => c.id === categoryId) ? categoryId : null
  const fromOptions = kind === 'expense' ? accounts : debit
  const cents = parseAmount(amount)
  const effectiveAccount = fromOptions.some((a) => a.id === accountId) ? accountId : fromOptions[0]?.id ?? null
  const problems = [
    cents === null || cents <= 0 ? 'Enter an amount above zero.' : null,
    kind !== 'payment' && !category ? 'Choose what it was for.' : null,
    !effectiveAccount ? (kind === 'expense' ? 'Add an account first.' : 'Add a debit account first.') : null,
    kind === 'payment' && !toAccountId ? 'Add a credit card first.' : null,
  ].filter(Boolean) as string[]

  const save = async () => {
    setTried(true)
    if (problems.length) return
    const body = {
      kind, amount_cents: cents, occurred_on: entry?.occurred_on ?? date, account_id: effectiveAccount,
      to_account_id: kind === 'payment' ? toAccountId : null, category_id: kind === 'payment' ? null : category, note,
    }
    const r = await action.run(() => (entry ? patch(`/finance/transactions/${entry.id}`, body) : post('/finance/transactions', { id, ...body })))
    if (r) {
      notifyChanged('money')
      if (!entry) { setAmount(''); setNote(''); setTried(false); setId(newId()) }
      onSaved?.()
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); save() }}>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented label="Type of entry" value={kind} onChange={setKind} options={KINDS} />
        {!entry && <span className="text-xs text-muted">for {formatShort(date)}</span>}
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor={`amt-${id}`} className="sr-only">Amount</label>
        <span className="text-2xl font-semibold text-muted">{currencySymbol(settings.currency)}</span>
        <input id={`amt-${id}`} inputMode="decimal" autoFocus={!entry} placeholder="0.00" value={amount}
          aria-invalid={tried && (cents === null || cents <= 0)}
          onChange={(e) => setAmount(e.target.value)}
          className="w-full min-w-0 rounded-lg border border-line bg-card px-3 py-2 text-2xl font-semibold tabular-nums focus:border-accent" />
      </div>

      {kind !== 'payment' && (
        <CategoryPicker legend={kind === 'expense' ? 'What was it for?' : 'Where is it from?'} name={`cat-${id}`}
          categories={cats} value={category} onChange={setCategoryId} />
      )}

      <div>
        <label htmlFor={`note-${id}`} className="mb-1.5 block text-sm font-medium">
          {kind === 'expense' ? 'Why / details' : 'Note'} <span className="font-normal text-muted">(optional)</span>
        </label>
        <input id={`note-${id}`} className={inputClass} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder={kind === 'expense' ? 'e.g. Lunch with the team' : kind === 'income' ? 'e.g. October salary' : 'e.g. Statement payment'} />
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">{kind === 'expense' ? 'Paid with' : kind === 'income' ? 'Into' : 'From'}</span>
        <AccountPicker accounts={fromOptions} value={effectiveAccount} onChange={setAccountId} label={kind === 'expense' ? 'Paid with' : kind === 'income' ? 'Into account' : 'Pay from'} />
      </div>
      {kind === 'payment' && (
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">To card</span>
          <AccountPicker accounts={credit} value={toAccountId} onChange={setToAccountId} label="Card to pay" />
        </div>
      )}

      {tried && problems.length > 0 && <p role="alert" className="text-sm text-danger">{problems[0]}</p>}
      {action.error && <ErrorNote message={action.error} />}
      <div>
        <Button type="submit" variant="primary" pending={action.pending}>
          {entry ? 'Save changes' : kind === 'expense' ? 'Add spending' : kind === 'income' ? 'Add money in' : 'Add card payment'}
        </Button>
      </div>
    </form>
  )
}

export function AccountPicker({ accounts, value, onChange, label }: {
  accounts: MoneyAccount[]; value: string | null; onChange: (id: string) => void; label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {accounts.map((a) => (
        <button key={a.id} type="button" role="radio" aria-checked={value === a.id} onClick={() => onChange(a.id)}
          className={cx('rounded-lg border px-3 py-1.5 text-sm transition',
            value === a.id ? 'border-accent bg-accent text-white' : 'border-line bg-card hover:border-accent/50')}>
          {a.name} <span className={cx('text-xs', value === a.id ? 'text-white/75' : 'text-muted')}>{a.type === 'debit' ? 'Debit' : 'Credit'}</span>
        </button>
      ))}
    </div>
  )
}

export function CategoryPicker({ legend, name, categories, value, onChange }: {
  legend: string; name: string; categories: MoneyCategory[]; value: string | null; onChange: (id: string) => void
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {categories.map((c) => (
          <label key={c.id} className={cx('cursor-pointer rounded-full border px-3 py-1 text-sm transition',
            value === c.id ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line bg-card hover:border-accent/40')}>
            <input type="radio" name={name} className="sr-only" checked={value === c.id} onChange={() => onChange(c.id)} />
            {c.name}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
