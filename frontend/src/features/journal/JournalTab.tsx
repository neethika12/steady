import { get } from '../../api'
import { Card, ErrorNote, Loading, cx } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort, relativeLabel } from '../../dates'
import { useLoad, useOnChanged } from '../../hooks'
import type { JournalListItem } from '../../types'
import { JournalSummary } from '../ai/JournalSummary'
import { JournalEditor } from './JournalEditor'

export function JournalTab() {
  const { date } = useApp()
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
      <JournalEditor key={date} date={date} />
      <div className="flex flex-col gap-4">
        <PastEntries />
        <JournalSummary />
      </div>
    </div>
  )
}

function PastEntries() {
  const { date, setDate, today } = useApp()
  const list = useLoad<JournalListItem[]>((s) => get('/journal', s), 'journal-list')
  useOnChanged(['journal'], list.reload)
  return (
    <Card aria-label="Past entries">
      <h3 className="mb-2 font-semibold">Recent entries</h3>
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <Loading />}
      {list.data?.length === 0 && <p className="text-sm text-muted">No entries in the last 90 days. Use the date picker above to open any day.</p>}
      <ul className="flex flex-col gap-1">
        {list.data?.map((e) => (
          <li key={e.entry_date}>
            <button type="button" onClick={() => setDate(e.entry_date)} aria-current={e.entry_date === date ? 'date' : undefined}
              className={cx('w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-paper', e.entry_date === date && 'bg-accent-soft')}>
              <span className="font-medium">{relativeLabel(e.entry_date, today) === formatShort(e.entry_date) ? formatShort(e.entry_date) : `${relativeLabel(e.entry_date, today)} · ${formatShort(e.entry_date)}`}</span>
              <span className="block truncate text-muted">{e.snippet || '(mood/energy only)'}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  )
}
