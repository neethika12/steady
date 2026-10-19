import { useState } from 'react'
import { del, get, newId, patch, post } from '../../api'
import { Badge, Button, Card, Dialog, ErrorNote, Loading, Segmented, cx, inputClass, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { WEEKDAY_NAMES, formatShort } from '../../dates'
import { notifyChanged, useAction, useLoad, useOnChanged } from '../../hooks'
import type { Frequency, MoneyAccount, MoneyCategory, MoneyKind, MoneyRecurring, MoneyRecurringSummary } from '../../types'
import { AccountPicker, CategoryPicker, KINDS } from './EntryForm'
import { currencySymbol, formatMoney, parseAmount } from './money'

const SCHEDULES: { frequency: Frequency; interval: number; label: string }[] = [
  { frequency: 'weekly', interval: 1, label: 'Every week' },
  { frequency: 'weekly', interval: 2, label: 'Every 2 weeks' },
  { frequency: 'monthly', interval: 1, label: 'Every month' },
  { frequency: 'monthly', interval: 3, label: 'Every 3 months' },
  { frequency: 'yearly', interval: 1, label: 'Every year' },
]
const key = (f: Frequency, n: number) => `${f}-${n}`

const ordinal = (n: number) => {
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${s}`
}

function scheduleLabel(f: Frequency, interval: number, anchor: string): string {
  const d = new Date(`${anchor}T00:00:00Z`)
  const day = d.getUTCDate()
  if (f === 'weekly') {
    const wd = WEEKDAY_NAMES[(d.getUTCDay() + 6) % 7]
    return interval === 1 ? `Every ${wd}` : `Every ${interval} weeks on ${wd}`
  }
  if (f === 'monthly') {
    const on = `on the ${ordinal(day)}${day >= 29 ? ' (or the last day)' : ''}`
    return interval === 1 ? `Monthly ${on}` : `Every ${interval} months ${on}`
  }
  const md = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(d)
  return interval === 1 ? `Yearly on ${md}` : `Every ${interval} years on ${md}`
}

/** Bills, subscriptions, salary: entries that happen on a schedule and are added automatically on their date. */
export function RecurringCard({ accounts, categories }: { accounts: MoneyAccount[]; categories: MoneyCategory[] }) {
  const { settings } = useApp()
  const data = useLoad<MoneyRecurringSummary>((s) => get('/finance/recurring', s), 'money-recurring')
  useOnChanged(['money'], data.reload)
  const [form, setForm] = useState<MoneyRecurring | 'new' | null>(null)
  const cur = settings.currency
  return (
    <Card aria-label="Repeating" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold">Repeating</h3>
          <p className="text-sm text-muted">Bills, subscriptions and salary. Each one is added automatically on its date.</p>
        </div>
        {data.data && data.data.bills_next_30_days_cents > 0 && (
          <p className="text-sm">Bills due in the next 30 days <strong className="tabular-nums">{formatMoney(data.data.bills_next_30_days_cents, cur)}</strong></p>
        )}
        <Button variant="primary" size="sm" onClick={() => setForm('new')}>+ Add repeating</Button>
      </div>
      {data.error && <ErrorNote message={data.error} onRetry={data.reload} />}
      {!data.data && !data.error && <Loading />}
      {data.data && data.data.rules.length === 0 && (
        <p className="rounded-lg bg-ink/[0.03] px-3 py-2.5 text-sm text-muted">
          Nothing repeating yet. Add rent, phone, streaming or your salary once, and it's recorded for you every time.
        </p>
      )}
      {data.data && data.data.rules.length > 0 && (
        <ul className="flex flex-col divide-y divide-line">
          {data.data.rules.map((r) => <RuleRow key={r.id} rule={r} cur={cur} onEdit={() => setForm(r)} />)}
        </ul>
      )}
      {form && (
        <Dialog title={form === 'new' ? 'Add a repeating entry' : `Edit “${form.name}”`} onClose={() => setForm(null)}>
          <RecurringForm accounts={accounts} categories={categories} rule={form === 'new' ? undefined : form} onSaved={() => setForm(null)} />
        </Dialog>
      )}
    </Card>
  )
}

function RuleRow({ rule, cur, onEdit }: { rule: MoneyRecurring; cur: string; onEdit: () => void }) {
  const { today } = useApp()
  const action = useAction()
  const toast = useToast()
  const [confirm, setConfirm] = useState(false)
  const what = rule.kind === 'payment' ? `Card payment to ${rule.to_account_name}` : rule.category_name
  const togglePause = async () => {
    if (await action.run(() => patch(`/finance/recurring/${rule.id}`, { paused: !rule.paused }))) notifyChanged('money')
  }
  return (
    <li className={cx('flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5', rule.paused && 'opacity-60')}>
      <div className="min-w-48 flex-1">
        <p className="truncate text-sm font-medium">
          {rule.name} <span className="font-normal text-muted">· {what}</span>
        </p>
        <p className="text-xs text-muted">
          {scheduleLabel(rule.frequency, rule.interval, rule.anchor_on)} · {rule.kind === 'income' ? 'into' : 'from'} {rule.account_name}
        </p>
      </div>
      <div className="text-right">
        <p className={cx('text-sm font-semibold tabular-nums', rule.kind === 'income' && 'text-teal')}>
          {rule.kind === 'income' ? '+' : rule.kind === 'expense' ? '−' : ''}{formatMoney(rule.amount_cents, cur)}
        </p>
        <p className="text-xs text-muted">
          {rule.paused ? <Badge>Paused</Badge> : rule.next_on === today ? 'Today' : `Next ${formatShort(rule.next_on!)}`}
        </p>
      </div>
      <div className="flex gap-1">
        <Button size="xs" variant="ghost" onClick={onEdit} aria-label={`Edit ${rule.name}`}>Edit</Button>
        <Button size="xs" variant="ghost" pending={action.pending} onClick={togglePause} aria-label={`${rule.paused ? 'Resume' : 'Pause'} ${rule.name}`}>
          {rule.paused ? 'Resume' : 'Pause'}
        </Button>
        <Button size="xs" variant="ghost" className="text-danger" onClick={() => setConfirm(true)} aria-label={`Stop ${rule.name}`}>Stop</Button>
      </div>
      {action.error && !confirm && <div className="w-full"><ErrorNote message={action.error} /></div>}
      {confirm && (
        <Dialog title={`Stop “${rule.name}”?`} onClose={() => setConfirm(false)} footer={<>
          <Button onClick={() => setConfirm(false)}>Keep it</Button>
          <Button variant="danger" pending={action.pending} onClick={async () => {
            if (await action.run(() => del(`/finance/recurring/${rule.id}`).then(() => true))) {
              setConfirm(false); toast(`${rule.name} stopped`); notifyChanged('money')
            }
          }}>Stop repeating</Button>
        </>}>
          <p className="text-sm">It won't be added again. Entries it already added stay in your history and balances.</p>
          <p className="mt-2 text-sm text-muted">To skip it for a while instead, use Pause.</p>
          {action.error && <ErrorNote message={action.error} />}
        </Dialog>
      )}
    </li>
  )
}

export function RecurringForm({ accounts, categories, rule, onSaved }: {
  accounts: MoneyAccount[]; categories: MoneyCategory[]; rule?: MoneyRecurring; onSaved: () => void
}) {
  const { settings, today } = useApp()
  const debit = accounts.filter((a) => a.type === 'debit')
  const credit = accounts.filter((a) => a.type === 'credit')
  const [id] = useState(newId)
  const [kind, setKind] = useState<MoneyKind>(rule?.kind ?? 'expense')
  const [name, setName] = useState(rule?.name ?? '')
  const [amount, setAmount] = useState(rule ? (rule.amount_cents / 100).toFixed(2) : '')
  const [categoryId, setCategoryId] = useState<string | null>(rule?.category_id ?? null)
  const [accountId, setAccountId] = useState<string | null>(rule?.account_id ?? accounts[0]?.id ?? null)
  const [toAccountId, setToAccountId] = useState<string | null>(rule?.to_account_id ?? credit[0]?.id ?? null)
  const [schedule, setSchedule] = useState(rule ? key(rule.frequency, rule.interval) : key('monthly', 1))
  const [nextOn, setNextOn] = useState<string>(rule?.next_on ?? today)
  const [tried, setTried] = useState(false)
  const action = useAction()

  const options = SCHEDULES.some((s) => key(s.frequency, s.interval) === schedule) || !rule
    ? SCHEDULES
    : [...SCHEDULES, { frequency: rule.frequency, interval: rule.interval, label: scheduleLabel(rule.frequency, rule.interval, rule.anchor_on) }]
  const picked = options.find((s) => key(s.frequency, s.interval) === schedule)!
  const cats = categories.filter((c) => c.kind === (kind === 'income' ? 'income' : 'expense') && !c.archived)
  const fromOptions = kind === 'expense' ? accounts : debit
  const effectiveAccount = fromOptions.some((a) => a.id === accountId) ? accountId : fromOptions[0]?.id ?? null
  const cents = parseAmount(amount)
  const problems = [
    !name.trim() ? 'Give it a name, like Rent or Netflix.' : null,
    cents === null || cents <= 0 ? 'Enter an amount above zero.' : null,
    kind !== 'payment' && !categoryId ? (kind === 'expense' ? 'Choose what it is for.' : 'Choose where it comes from.') : null,
    !effectiveAccount ? 'Add an account first.' : null,
    kind === 'payment' && !toAccountId ? 'Add a credit card first.' : null,
    !nextOn || nextOn < today ? 'Choose today or a later date.' : null,
  ].filter(Boolean) as string[]

  const save = async () => {
    setTried(true)
    if (problems.length) return
    const body = {
      name: name.trim(), kind, amount_cents: cents, account_id: effectiveAccount,
      to_account_id: kind === 'payment' ? toAccountId : null, category_id: kind === 'payment' ? null : categoryId,
      frequency: picked.frequency, interval: picked.interval, next_on: nextOn,
    }
    const r = await action.run(() => (rule ? patch(`/finance/recurring/${rule.id}`, body) : post('/finance/recurring', { id, ...body })))
    if (r) { notifyChanged('money'); onSaved() }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); save() }}>
      <Segmented label="Type of entry" value={kind} onChange={(k) => { setKind(k); setCategoryId(null) }} options={KINDS} />

      <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
        <div>
          <label htmlFor={`rname-${id}`} className="mb-1.5 block text-sm font-medium">Name</label>
          <input id={`rname-${id}`} className={inputClass} maxLength={60} value={name} autoFocus={!rule}
            aria-invalid={tried && !name.trim()} onChange={(e) => setName(e.target.value)}
            placeholder={kind === 'expense' ? 'e.g. Rent, Netflix, Phone bill' : kind === 'income' ? 'e.g. Salary' : 'e.g. Card autopay'} />
        </div>
        <div>
          <label htmlFor={`ramt-${id}`} className="mb-1.5 block text-sm font-medium">Amount</label>
          <div className="flex items-center gap-1.5">
            <span className="text-muted">{currencySymbol(settings.currency)}</span>
            <input id={`ramt-${id}`} inputMode="decimal" placeholder="0.00" className={cx(inputClass, 'tabular-nums')} value={amount}
              aria-invalid={tried && (cents === null || cents <= 0)} onChange={(e) => setAmount(e.target.value)} />
          </div>
        </div>
      </div>

      {kind !== 'payment' && (
        <CategoryPicker legend={kind === 'expense' ? 'What is it for?' : 'Where is it from?'} name={`rcat-${id}`}
          categories={cats} value={categoryId} onChange={setCategoryId} />
      )}

      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">{kind === 'expense' ? 'Paid with' : kind === 'income' ? 'Into' : 'From'}</span>
        <AccountPicker accounts={fromOptions} value={effectiveAccount} onChange={setAccountId}
          label={kind === 'expense' ? 'Paid with' : kind === 'income' ? 'Into account' : 'Pay from'} />
      </div>
      {kind === 'payment' && (
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">To card</span>
          <AccountPicker accounts={credit} value={toAccountId} onChange={setToAccountId} label="Card to pay" />
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={`rsched-${id}`} className="mb-1.5 block text-sm font-medium">Repeats</label>
          <select id={`rsched-${id}`} className={inputClass} value={schedule} onChange={(e) => setSchedule(e.target.value)}>
            {options.map((s) => <option key={key(s.frequency, s.interval)} value={key(s.frequency, s.interval)}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`rnext-${id}`} className="mb-1.5 block text-sm font-medium">{rule ? 'Next one on' : 'First one on'}</label>
          <input id={`rnext-${id}`} type="date" className={inputClass} min={today} value={nextOn}
            aria-invalid={tried && (!nextOn || nextOn < today)} onChange={(e) => setNextOn(e.target.value)} />
        </div>
      </div>
      {nextOn && nextOn >= today && (
        <p className="text-sm text-muted">
          {scheduleLabel(picked.frequency, picked.interval, nextOn)}, starting {nextOn === today ? 'today' : formatShort(nextOn)}.
          {' '}Each one is added on its date as a normal entry you can edit or delete.
          {rule && ' Changes apply from the next one; earlier entries stay as they are.'}
        </p>
      )}

      {tried && problems.length > 0 && <p role="alert" className="text-sm text-danger">{problems[0]}</p>}
      {action.error && <ErrorNote message={action.error} />}
      <div>
        <Button type="submit" variant="primary" pending={action.pending}>{rule ? 'Save changes' : 'Add repeating'}</Button>
      </div>
    </form>
  )
}
