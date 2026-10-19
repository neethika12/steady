import { useState } from 'react'
import { del, get } from '../../api'
import { Badge, Button, Card, Dialog, Empty, ErrorNote, Loading, cx, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { formatLong, formatShort } from '../../dates'
import { notifyChanged, useAction, useLoad, useOnChanged } from '../../hooks'
import type { MoneyCategory, MoneyDay, MoneyEntry, MoneyMonth, MoneyOverview } from '../../types'
import { EntryForm } from './EntryForm'
import { ManageAccounts } from './ManageAccounts'
import { RecurringCard } from './Recurring'
import { SplitwiseCard } from './Splitwise'
import { MoneyInsights } from './Insights'
import { SetupWizard } from './SetupWizard'
import { formatMoney } from './money'

/** Money: what you have, what you owe, and what you spent each day. No AI is involved here. */
export function MoneyTab() {
  const overview = useLoad<MoneyOverview>((s) => get('/finance/overview', s), 'money-overview')
  useOnChanged(['money'], overview.reload)
  if (overview.error) return <ErrorNote message={overview.error} onRetry={overview.reload} />
  if (!overview.data) return <Loading />
  if (!overview.data.set_up) return <SetupWizard onDone={overview.reload} />
  return <Dashboard overview={overview.data} />
}

function Dashboard({ overview }: { overview: MoneyOverview }) {
  const { date, settings } = useApp()
  const cur = settings.currency
  const day = useLoad<MoneyDay>((s) => get(`/finance/day?date=${date}`, s), `money-day-${date}`)
  const month = date.slice(0, 7)
  const monthData = useLoad<MoneyMonth>((s) => get(`/finance/month?month=${month}`, s), `money-month-${month}`)
  const cats = useLoad<MoneyCategory[]>((s) => get('/finance/categories', s), 'money-cats')
  const reload = () => { day.reload(); monthData.reload() }
  useOnChanged(['money'], reload)
  const [manage, setManage] = useState(false)
  const [editing, setEditing] = useState<MoneyEntry | null>(null)
  const active = overview.accounts.filter((a) => !a.archived)

  return (
    <div className="flex flex-col gap-4">
      {/* Accounts */}
      <section aria-label="Accounts" className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Total label="Money available" hint="All debit accounts" cents={overview.available_cents} cur={cur} tone="text-teal" />
          <Total label="Owed on cards" hint="All credit cards" cents={overview.owed_cents} cur={cur} tone="text-danger" />
          <Total label="Net" hint="Available − cards + Splitwise get − pay" cents={overview.net_cents} cur={cur} tone="text-ink" />
        </div>
        <div className="flex flex-wrap items-stretch gap-2">
          {active.map((a) => (
            <div key={a.id} className="min-w-44 flex-1 rounded-xl border border-line bg-card px-4 py-3 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
              <p className="flex items-center gap-2 text-xs font-medium text-muted">
                <span aria-hidden className={cx('size-2 rounded-full', a.type === 'debit' ? 'bg-teal' : 'bg-danger')} />
                {a.type === 'debit' ? 'Debit' : 'Credit card'}
              </p>
              <p className="mt-0.5 truncate text-sm font-semibold">{a.name}</p>
              <p className={cx('mt-1 text-lg font-semibold tabular-nums', a.type === 'credit' && a.balance_cents > 0 && 'text-danger')}>
                {formatMoney(a.balance_cents, cur)}
                <span className="ml-1 text-xs font-normal text-muted">{a.type === 'debit' ? 'available' : 'owed'}</span>
              </p>
            </div>
          ))}
          <SplitwiseCard data={overview.splitwise} />
          <Button className="self-center" onClick={() => setManage(true)}>Manage accounts</Button>
        </div>
      </section>

      <div className="@container">
        <div className="grid items-start gap-4 @3xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          {/* Add */}
          <Card aria-label="Add money entry">
            <h3 className="mb-3 font-semibold">Add for {formatLong(date)}</h3>
            {cats.data ? <EntryForm date={date} accounts={active} categories={cats.data} /> : <Loading />}
          </Card>

          {/* The day */}
          <Card aria-label="Day entries" className="flex flex-col gap-3">
            <div className="flex items-baseline gap-2">
              <h3 className="font-semibold">{formatShort(date)}</h3>
              {day.data && <span className="ml-auto text-sm">Spent <strong className="tabular-nums">{formatMoney(day.data.spent_cents, cur)}</strong></span>}
            </div>
            {day.error && <ErrorNote message={day.error} onRetry={day.reload} />}
            {!day.data && !day.error && <Loading />}
            {day.data && day.data.transactions.length === 0 && day.data.scheduled.length === 0 && (
              <Empty title="Nothing recorded for this day">Add what you spent, and what it was for.</Empty>
            )}
            <ul className="flex flex-col divide-y divide-line">
              {day.data?.transactions.map((t) => <EntryRow key={t.id} entry={t} cur={cur} onEdit={() => setEditing(t)} />)}
            </ul>
            {day.data && day.data.scheduled.length > 0 && (
              <div aria-label="Scheduled">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Scheduled for this day</p>
                <ul className="flex flex-col divide-y divide-line rounded-lg border border-dashed border-line px-3">
                  {day.data.scheduled.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 py-2 text-sm text-muted">
                      <span className="min-w-0 flex-1 truncate">{r.name} · {r.kind === 'income' ? 'into' : 'from'} {r.account_name}</span>
                      <span className="tabular-nums">{r.kind === 'income' ? '+' : r.kind === 'expense' ? '−' : ''}{formatMoney(r.amount_cents, cur)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </div>
      </div>

      {cats.data && <RecurringCard accounts={active} categories={cats.data} />}

      <MonthCard data={monthData.data} error={monthData.error} cur={cur} />

      <MoneyInsights />

      {manage && <ManageAccounts accounts={overview.accounts} onClose={() => setManage(false)} />}
      {editing && cats.data && (
        <Dialog title="Edit entry" onClose={() => setEditing(null)}>
          <EntryForm date={editing.occurred_on} accounts={active} categories={cats.data} entry={editing} onSaved={() => setEditing(null)} />
        </Dialog>
      )}
    </div>
  )
}

function Total({ label, hint, cents, cur, tone }: { label: string; hint: string; cents: number; cur: string; tone: string }) {
  return (
    <div className="rounded-xl border border-line bg-card px-4 py-3 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={cx('mt-1 text-2xl font-semibold tabular-nums', tone)}>{formatMoney(cents, cur)}</p>
      <p className="text-xs text-muted">{hint}</p>
    </div>
  )
}

function EntryRow({ entry, cur, onEdit }: { entry: MoneyEntry; cur: string; onEdit: () => void }) {
  const [confirm, setConfirm] = useState(false)
  const action = useAction()
  const toast = useToast()
  const sign = entry.kind === 'expense' ? '−' : entry.kind === 'income' ? '+' : ''
  const what = entry.kind === 'payment' ? `Card payment to ${entry.to_account_name}` : entry.category_name
  return (
    <li className="flex items-center gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{what}{entry.note && <span className="font-normal text-muted"> · {entry.note}</span>}</p>
        <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted">
          {entry.kind === 'income' ? 'Into' : 'From'} {entry.account_name}
          {entry.recurring_id && <Badge tone="accent" title="Added automatically by a repeating entry">Repeats</Badge>}
        </p>
      </div>
      <span className={cx('whitespace-nowrap text-sm font-semibold tabular-nums',
        entry.kind === 'expense' ? 'text-ink' : entry.kind === 'income' ? 'text-teal' : 'text-muted')}>
        {sign}{formatMoney(entry.amount_cents, cur)}
      </span>
      <Button size="xs" variant="ghost" onClick={onEdit} aria-label={`Edit ${what}`}>Edit</Button>
      <Button size="xs" variant="ghost" className="text-danger" onClick={() => setConfirm(true)} aria-label={`Delete ${what}`}>Delete</Button>
      {confirm && (
        <Dialog title="Delete this entry?" onClose={() => setConfirm(false)} footer={<>
          <Button onClick={() => setConfirm(false)}>Keep it</Button>
          <Button variant="danger" pending={action.pending} onClick={async () => {
            if (await action.run(() => del(`/finance/transactions/${entry.id}`).then(() => true))) {
              setConfirm(false); toast('Entry deleted'); notifyChanged('money')
            }
          }}>Delete</Button>
        </>}>
          <p className="text-sm">{what}: <strong>{formatMoney(entry.amount_cents, cur)}</strong> on {formatShort(entry.occurred_on)}. Balances will be recalculated.</p>
          {action.error && <ErrorNote message={action.error} />}
        </Dialog>
      )}
    </li>
  )
}

function MonthCard({ data, error, cur }: { data: MoneyMonth | null; error: string | null; cur: string }) {
  if (error) return <ErrorNote message={error} />
  if (!data) return null
  const change = data.spent_cents - data.previous_month_spent_cents
  const monthName = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${data.start}T00:00:00Z`))
  return (
    <Card aria-label="This month" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <h3 className="font-semibold">{monthName}</h3>
        <p className="text-sm">Spent <strong className="tabular-nums">{formatMoney(data.spent_cents, cur)}</strong></p>
        {data.income_cents > 0 && <p className="text-sm">Money in <strong className="tabular-nums text-teal">{formatMoney(data.income_cents, cur)}</strong></p>}
        {data.avg_per_day_cents !== null && <p className="text-sm text-muted">About {formatMoney(data.avg_per_day_cents, cur)} a day</p>}
        {data.previous_month_spent_cents > 0 && (
          <p className="text-sm text-muted">
            {change === 0 ? 'Same as last month' : `${formatMoney(Math.abs(change), cur)} ${change > 0 ? 'more' : 'less'} than last month`}
          </p>
        )}
      </div>
      {data.by_category.length === 0 ? <p className="text-sm text-muted">No spending recorded this month.</p> : (
        <ul className="flex flex-col gap-2.5" aria-label="Spending by category">
          {data.by_category.map((c) => (
            <li key={c.category_id}>
              <div className="flex justify-between text-sm">
                <span>{c.name}</span>
                <span className="tabular-nums text-muted">{formatMoney(c.spent_cents, cur)} · {c.share_pct ?? 0}%</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-ink/5">
                <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(2, c.share_pct ?? 0)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
