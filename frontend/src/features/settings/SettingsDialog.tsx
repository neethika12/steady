import { useMemo, useState } from 'react'
import { errorMessage, post, put } from '../../api'
import { Button, Dialog, ErrorNote, Field, Notice, inputClass, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { WEEKDAY_NAMES } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import { AiStatusPanel } from '../ai/AiStatus'
import { TimelineHoursForm } from '../../components/TimelineHours'
import { CURRENCIES } from '../money/money'

interface ImportReport {
  dry_run: boolean
  collections: Record<string, { in_file: number; imported: number; skipped_existing: number; conflicts: number }>
  settings_applied: boolean
}

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const { settings, reloadSettings } = useApp()
  const [tz, setTz] = useState(settings.timezone)
  const [weekStart, setWeekStart] = useState(settings.week_start)
  const [currency, setCurrency] = useState(settings.currency)
  const save = useAction()
  const toast = useToast()
  const zones = useMemo(() => {
    try { return (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone') ?? [] } catch { return [] }
  }, [])

  return (
    <Dialog title="Settings" onClose={onClose} wide footer={<Button onClick={onClose}>Close</Button>}>
      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">Calendar</h3>
          <p className="text-sm text-muted">
            Every “day” in Steady (tasks, habits, journal) is a calendar day in this timezone, including across daylight-saving changes.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Timezone" htmlFor="set-tz">
              <input id="set-tz" list="tz-list" className={inputClass} value={tz} onChange={(e) => setTz(e.target.value)} />
              <datalist id="tz-list">{zones.map((z) => <option key={z} value={z} />)}</datalist>
            </Field>
            <Field label="Currency (Money tab)" htmlFor="set-cur">
              <select id="set-cur" className={inputClass} value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {Array.from(new Set([currency, ...CURRENCIES])).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Week starts on" htmlFor="set-ws">
              <select id="set-ws" className={inputClass} value={weekStart} onChange={(e) => setWeekStart(Number(e.target.value))}>
                {WEEKDAY_NAMES.map((n, i) => <option key={n} value={i}>{n}</option>)}
              </select>
            </Field>
          </div>
          <div>
            <Button variant="primary" size="sm" pending={save.pending} onClick={async () => {
              if (await save.run(() => put('/settings', { timezone: tz, week_start: weekStart, currency }))) {
                toast('Settings saved'); reloadSettings(); notifyChanged('tasks', 'habits', 'journal', 'money')
              }
            }}>Save calendar settings</Button>
          </div>
          {save.error && <ErrorNote message={save.error} />}
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">Timeline hours</h3>
          <p className="text-sm text-muted">The hours your Day timeline shows. Night owl? Choose an end after midnight, like 11 AM to 2 AM.</p>
          <TimelineHoursForm />
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">Export and import</h3>
          <p className="text-sm text-muted">
            Export downloads everything as one JSON file. Keep it somewhere safe: it contains your journal.
            Exports are useful copies, but regular database backups are still recommended (see the README).
          </p>
          <div><a href="/api/data/export" download className="inline-flex min-h-8 items-center rounded-lg border border-line bg-card px-2.5 text-sm font-medium hover:bg-paper">Download export (.json)</a></div>
          <ImportSection />
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="font-semibold">AI</h3>
          <AiStatusPanel />
        </section>

        <Notice>
          Your data is private to your account. To leave, use the account menu (top right): <em>Delete account</em>
          removes everything. Download an export first if you want a copy.
        </Notice>
      </div>
    </Dialog>
  )
}

function ImportSection() {
  const [file, setFile] = useState<unknown>(null)
  const [fileName, setFileName] = useState('')
  const [report, setReport] = useState<ImportReport | null>(null)
  const [readError, setReadError] = useState<string | null>(null)
  const action = useAction()
  const toast = useToast()

  const choose = async (f: File | undefined) => {
    setReport(null); setReadError(null); setFile(null)
    if (!f) return
    setFileName(f.name)
    try {
      const parsed = JSON.parse(await f.text())
      setFile(parsed)
      const r = await action.run(() => post<ImportReport>('/data/import?dry_run=true', parsed))
      if (r) setReport(r)
    } catch (err) {
      setReadError(err instanceof SyntaxError ? 'That file is not valid JSON.' : errorMessage(err))
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Field label="Import a Steady export" htmlFor="imp-file"
        hint="Records already here (same id) are skipped, never overwritten. A journal entry for a date that already has one, or a duplicate check-in, is reported as a conflict and skipped. Settings in the file are not applied.">
        <input id="imp-file" type="file" accept="application/json,.json" className="text-sm" onChange={(e) => choose(e.target.files?.[0])} />
      </Field>
      {readError && <ErrorNote message={readError} />}
      {action.error && <ErrorNote message={action.error} />}
      {report && (
        <div className="rounded-lg border border-line p-3 text-sm">
          <p className="mb-2 font-medium">{report.dry_run ? `Preview of ${fileName} (nothing imported yet)` : 'Import complete'}</p>
          <table className="w-full text-left text-xs">
            <thead className="text-muted"><tr><th className="font-medium">Records</th><th className="font-medium">In file</th><th className="font-medium">New</th><th className="font-medium">Already here</th><th className="font-medium">Conflicts</th></tr></thead>
            <tbody>
              {Object.entries(report.collections).map(([k, c]) => (
                <tr key={k} className="border-t border-line"><td className="py-1">{k.replace(/_/g, ' ')}</td><td>{c.in_file}</td><td>{c.imported}</td><td>{c.skipped_existing}</td><td>{c.conflicts}</td></tr>
              ))}
            </tbody>
          </table>
          {report.dry_run && (
            <Button className="mt-3" size="sm" variant="primary" pending={action.pending} onClick={async () => {
              const r = await action.run(() => post<ImportReport>('/data/import?dry_run=false', file))
              if (r) { setReport(r); toast('Import complete'); notifyChanged('tasks', 'habits', 'journal') }
            }}>Import new records</Button>
          )}
        </div>
      )}
    </div>
  )
}
