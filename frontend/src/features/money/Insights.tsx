import { get, post } from '../../api'
import { Button, Card, ErrorNote, Loading, Spinner, cx } from '../../components/ui'
import { useApp } from '../../context'
import { useLoad, useOnChanged } from '../../hooks'
import { AiError, AiLabel, useAiEnabled, useAiStatus, useAiWords } from '../ai/AiStatus'
import { useAiRequest } from '../ai/useAiRequest'
import { formatMoney } from './money'

interface TrendMonth {
  month: string; complete: boolean; days: number; days_in_month: number; tracked: boolean
  spent_cents: number; income_cents: number; saved_cents: number; savings_rate_pct: number | null
}
interface TrendCategory {
  category_id: string; name: string; avg_monthly_cents: number | null
  this_month_cents: number; usual_by_today_cents: number | null; change_pct: number | null
}
interface Trends {
  months: TrendMonth[]; full_months_counted: number; avg_monthly_spent_cents: number | null
  this_month_cents: number; usual_by_today_cents: number | null; day_of_month: number; categories: TrendCategory[]
  repeating_monthly_cents: number; repeating_bills: { name: string; monthly_cents: number }[]
}
interface Support { kind: 'month' | 'category' | 'bill'; label: string; [k: string]: unknown }
interface Point { text: string; support: Support[] }
interface Review {
  trends: Point[]
  cut_back: { category: string; reduce_pct: number; text: string; based_on: string; based_on_cents: number
    saving_monthly_cents: number; saving_yearly_cents: number }[]
  save_tips: Point[]
  possible_saving_monthly_cents: number
}

const monthName = (ym: string, long = false) =>
  new Intl.DateTimeFormat(undefined, { month: long ? 'long' : 'short', year: long ? 'numeric' : undefined, timeZone: 'UTC' })
    .format(new Date(`${ym}-01T00:00:00Z`))

/** Money insights: trends calculated by the app, plus optional saving tips from the AI. */
export function MoneyInsights() {
  const { settings } = useApp()
  const cur = settings.currency
  const data = useLoad<Trends>((s) => get('/finance/trends', s), 'money-trends')
  useOnChanged(['money'], data.reload)
  const ai = useAiRequest<Review>()
  const { status } = useAiStatus()
  const words = useAiWords()
  const aiEnabled = useAiEnabled()
  const t = data.data
  const months = t?.months.filter((m) => m.tracked) ?? []
  const money = (c: number | null | undefined) => (c === null || c === undefined ? '—' : formatMoney(c, cur))

  return (
    <Card aria-label="Money insights" className="flex flex-col gap-4">
      <div>
        <h3 className="font-semibold">Insights</h3>
        <p className="text-sm text-muted">Your trends, calculated from your entries.</p>
      </div>
      {data.error && <ErrorNote message={data.error} onRetry={data.reload} />}
      {!t && !data.error && <Loading />}
      {t && months.length === 0 && <p className="text-sm text-muted">Add some spending and your trends will appear here.</p>}
      {t && months.length > 0 && (
        <>
          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }}>
            {months.map((m) => (
              <div key={m.month} className={cx('rounded-lg border px-3 py-2', m.complete ? 'border-line' : 'border-accent/40 bg-accent-soft/40')}>
                <p className="text-xs font-medium text-muted">{monthName(m.month)}{!m.complete && ' · so far'}</p>
                <p className="mt-0.5 text-sm">Spent <strong className="tabular-nums">{money(m.spent_cents)}</strong></p>
                {m.income_cents > 0 && <p className="text-sm">In <span className="tabular-nums text-teal">{money(m.income_cents)}</span></p>}
                {m.income_cents > 0 && (
                  <p className={cx('text-xs', m.saved_cents >= 0 ? 'text-teal' : 'text-danger')}>
                    {m.saved_cents >= 0 ? 'Saved' : 'Overspent'} {money(Math.abs(m.saved_cents))}
                    {m.savings_rate_pct !== null && m.saved_cents >= 0 && ` (${m.savings_rate_pct}%)`}
                  </p>
                )}
              </div>
            ))}
          </div>
          <p className="text-sm text-muted">
            {t.avg_monthly_spent_cents !== null && t.usual_by_today_cents !== null
              ? <>On average you spend <strong className="text-ink">{money(t.avg_monthly_spent_cents)}</strong> a month. So far this month: <strong className="text-ink">{money(t.this_month_cents)}</strong>, against <strong className="text-ink">{money(t.usual_by_today_cents)}</strong> usually by day {t.day_of_month}.</>
              : <>So far this month: <strong className="text-ink">{money(t.this_month_cents)}</strong>. Comparisons start after your first full month of tracking.</>}
            {t.repeating_monthly_cents > 0 && <> Repeating bills come to about <strong className="text-ink">{money(t.repeating_monthly_cents)}</strong> a month.</>}
          </p>
          {t.categories.length > 0 && (
            <table className="w-full text-sm" aria-label="Spending by category over time">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="pb-1 font-medium">Category</th>
                  <th className="pb-1 text-right font-medium">Avg / month</th>
                  <th className="pb-1 text-right font-medium">This month</th>
                  <th className="pb-1 text-right font-medium" title={`Compared with what you usually spent by day ${t.day_of_month}`}>vs usual</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {t.categories.slice(0, 8).map((c) => (
                  <tr key={c.category_id}>
                    <td className="py-1.5">{c.name}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(c.avg_monthly_cents)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(c.this_month_cents)}</td>
                    <td className="py-1.5 text-right">
                      {c.change_pct === null ? <span className="text-muted">—</span> : (
                        <span className={cx('tabular-nums', c.change_pct > 5 ? 'text-danger' : c.change_pct < -5 ? 'text-teal' : 'text-muted')}
                          title={`Usually ${money(c.usual_by_today_cents)} by day ${t.day_of_month}`}>
                          {c.change_pct > 0 ? '↑' : c.change_pct < 0 ? '↓' : ''}{Math.abs(c.change_pct)}%
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {t && months.length > 0 && aiEnabled && (
        <div className="flex flex-col gap-3 rounded-lg border border-line p-3" aria-label="AI saving tips">
          {!ai.data && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="primary" pending={ai.pending} onClick={() => ai.run(() => post<Review>('/ai/money-review'))}>
                Get saving tips with {words.name}
              </Button>
              <span className="text-xs text-muted">Sends monthly and category totals and repeating bill names {words.to}. No notes, account names or balances.</span>
            </div>
          )}
          {ai.pending && <Spinner label={words.thinking} />}
          {ai.error !== null && <AiError error={ai.error} />}
          {ai.data && (
            <div className="flex flex-col gap-4 text-sm">
              <AiLabel model={status?.model} />
              <section>
                <h4 className="font-semibold">Trends <span className="font-normal text-muted">(from your figures)</span></h4>
                <ul className="mt-1 flex flex-col gap-2">
                  {ai.data.trends.map((p, i) => (
                    <li key={i}>
                      <p>{p.text}</p>
                      <details className="text-xs text-muted">
                        <summary className="cursor-pointer">Based on {p.support.map((s) => s.kind === 'month' ? monthName(s.label, true) : s.label).join(', ')}</summary>
                        <ul className="mt-1 list-inside list-disc">
                          {p.support.map((s, j) => <li key={j}>{supportLine(s, money)}</li>)}
                        </ul>
                      </details>
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h4 className="font-semibold">Where to cut back</h4>
                <ul className="mt-1 flex flex-col gap-2">
                  {ai.data.cut_back.map((c) => (
                    <li key={c.category} className="rounded-lg bg-ink/[0.03] px-3 py-2">
                      <p className="flex flex-wrap items-baseline gap-x-2">
                        <strong>{c.category}</strong>
                        <span className="text-muted">cut {c.reduce_pct}% of {money(c.based_on_cents)} ({c.based_on})</span>
                        <span className="ml-auto font-medium text-teal">save about {money(c.saving_monthly_cents)} a month · {money(c.saving_yearly_cents)} a year</span>
                      </p>
                      <p className="mt-0.5">{c.text}</p>
                    </li>
                  ))}
                </ul>
                {ai.data.cut_back.length > 1 && (
                  <p className="mt-2">Together: about <strong className="text-teal">{money(ai.data.possible_saving_monthly_cents)}</strong> a month
                    (<strong className="text-teal">{money(ai.data.possible_saving_monthly_cents * 12)}</strong> a year).</p>
                )}
                <p className="mt-1 text-xs text-muted">Savings are calculated by the app from your figures, not by the AI.</p>
              </section>
              <section>
                <h4 className="font-semibold">Ways to save <span className="font-normal text-muted">(ideas to try; nothing is changed)</span></h4>
                <ul className="mt-1 list-inside list-disc">{ai.data.save_tips.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
              </section>
              <div><Button size="sm" variant="ghost" onClick={ai.reset}>Clear</Button></div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function supportLine(s: Support, money: (c: number | null | undefined) => string): string {
  if (s.kind === 'month') return `${monthName(s.label, true)}: spent ${money(s.spent_cents as number)}, money in ${money(s.income_cents as number)}${s.complete ? '' : ' (so far)'}`
  if (s.kind === 'category') return `${s.label}: ${money(s.avg_monthly_cents as number | null)} a month on average, ${money(s.this_month_cents as number)} this month`
  return `${s.label}: about ${money(s.monthly_cents as number)} a month`
}
