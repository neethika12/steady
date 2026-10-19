import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, errorMessage, get, put } from '../../api'
import { Button, Card, ErrorNote, Field, Loading, Notice, Segmented, cx, inputClass } from '../../components/ui'
import { useApp } from '../../context'
import { formatDateTime } from '../../dates'
import { notifyChanged } from '../../hooks'
import type { JournalEntry, JournalFields } from '../../types'
import { JournalPrompts } from '../ai/JournalPrompts'
import { clearDraft, pickFields, readDraft, sameFields, writeDraft } from './draft'

type Status = 'loading' | 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict' | 'load_error'

const MOODS = [
  { value: '1', label: 'Very low' }, { value: '2', label: 'Low' }, { value: '3', label: 'Okay' },
  { value: '4', label: 'Good' }, { value: '5', label: 'Very good' },
]
const ENERGY = [
  { value: '1', label: 'Very low' }, { value: '2', label: 'Low' }, { value: '3', label: 'Medium' },
  { value: '4', label: 'High' }, { value: '5', label: 'Very high' },
]

const EMPTY: JournalFields = { body: '', mood: null, energy: null, went_well: '', was_difficult: '', on_mind: '' }

export function JournalEditor({ date }: { date: string }) {
  const { today, settings } = useApp()
  const [fields, setFields] = useState<JournalFields>(EMPTY)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState<JournalEntry | null>(null)
  const [recovered, setRecovered] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const fieldsRef = useRef(fields)
  const versionRef = useRef(0)
  const serverRef = useRef<JournalFields>(EMPTY)
  const inFlight = useRef(false)
  const again = useRef(false)
  const future = date > today

  // Load the entry, then check for an unsaved local draft.
  const load = useCallback(async () => {
    setStatus('loading')
    try {
      const entry = await get<JournalEntry>(`/journal/${date}`)
      versionRef.current = entry.version
      serverRef.current = pickFields(entry)
      setUpdatedAt(entry.updated_at)
      const draft = readDraft(date)
      if (draft && !sameFields(draft.fields, serverRef.current)) {
        if (draft.baseVersion === entry.version) {
          // Unsaved edits made on top of the current version: restore and save them.
          fieldsRef.current = draft.fields
          setFields(draft.fields)
          setRecovered(draft.savedAt)
          setStatus('dirty')
          return
        }
        // The entry changed elsewhere after the draft was made: let the user decide.
        fieldsRef.current = draft.fields
        setFields(draft.fields)
        setConflict(entry)
        setStatus('conflict')
        return
      }
      if (draft) clearDraft(date)
      fieldsRef.current = serverRef.current
      setFields(serverRef.current)
      setStatus('idle')
    } catch (err) {
      setError(errorMessage(err))
      setStatus('load_error')
    }
  }, [date])

  useEffect(() => { load() }, [load])

  const saveNow = useCallback(async () => {
    if (inFlight.current) { again.current = true; return }
    const sending = fieldsRef.current
    if (sameFields(sending, serverRef.current)) { clearDraft(date); setStatus('saved'); return }
    inFlight.current = true
    setStatus('saving')
    try {
      const saved = await put<JournalEntry>(`/journal/${date}`, { ...sending, base_version: versionRef.current })
      versionRef.current = saved.version
      serverRef.current = sending
      setUpdatedAt(saved.updated_at)
      setError(null)
      if (sameFields(fieldsRef.current, sending)) {
        clearDraft(date)
        setStatus('saved')
      } else {
        setStatus('dirty')
      }
      notifyChanged('journal')
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.code === 'journal_conflict') {
        const current = (err.detail as { current: JournalEntry }).current
        setConflict(current)
        setStatus('conflict')
      } else {
        setError(errorMessage(err))
        setStatus('error')
      }
    } finally {
      inFlight.current = false
      if (again.current) { again.current = false; void saveNow() }
    }
  }, [date])

  // Debounced autosave while typing.
  useEffect(() => {
    if (status !== 'dirty') return
    const t = setTimeout(saveNow, 1000)
    return () => clearTimeout(t)
  }, [fields, status, saveNow])

  // Save straight away when leaving this day (switching date or tab).
  useEffect(() => () => {
    if (!sameFields(fieldsRef.current, serverRef.current) && !inFlight.current) {
      put(`/journal/${date}`, { ...fieldsRef.current, base_version: versionRef.current })
        .then(() => { clearDraft(date); notifyChanged('journal') })
        .catch(() => { /* the local draft is kept and offered next time */ })
    }
  }, [date])

  const update = (patch: Partial<JournalFields>) => {
    const next = { ...fieldsRef.current, ...patch }
    fieldsRef.current = next
    setFields(next)
    writeDraft(date, next, versionRef.current)
    if (status !== 'conflict') setStatus('dirty')
  }

  const keepMine = async () => {
    if (!conflict) return
    versionRef.current = conflict.version
    serverRef.current = pickFields(conflict)
    setConflict(null)
    writeDraft(date, fieldsRef.current, versionRef.current)
    setStatus('dirty')
    await saveNow()
  }
  const useTheirs = () => {
    if (!conflict) return
    versionRef.current = conflict.version
    serverRef.current = pickFields(conflict)
    fieldsRef.current = serverRef.current
    setFields(serverRef.current)
    setUpdatedAt(conflict.updated_at)
    clearDraft(date)
    setConflict(null)
    setStatus('idle')
  }

  if (status === 'loading') return <Card><Loading /></Card>
  if (status === 'load_error') return <ErrorNote message={`Couldn't load this entry: ${error}`} onRetry={load} />

  return (
    <Card className="flex flex-col gap-4" aria-label="Journal entry">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">Entry</h3>
        <span className="hidden text-xs text-muted sm:inline">Writing it down is a kindness to yourself.</span>
        <SaveStatus status={status} />
        {updatedAt && <span className="text-xs text-muted">Last saved {formatDateTime(updatedAt, settings.timezone)}</span>}
        {(status === 'error' || status === 'dirty') && <Button size="sm" className="ml-auto" onClick={saveNow}>Save now</Button>}
      </div>
      {future && <Notice tone="warn">This day hasn’t happened yet. Journal entries can be written for today or earlier.</Notice>}
      {recovered && status !== 'conflict' && (
        <Notice>Restored unsaved changes from {formatDateTime(recovered, settings.timezone)} that hadn’t reached the server.</Notice>
      )}
      {status === 'error' && error && (
        <ErrorNote message={`Couldn’t save: ${error} Your text is kept on this device and will be offered again if you reload.`} onRetry={saveNow} />
      )}
      {status === 'conflict' && conflict && <ConflictPanel mine={fields} theirs={conflict} onKeepMine={keepMine} onUseTheirs={useTheirs} />}

      <Field label="Free writing" htmlFor="j-body">
        <textarea id="j-body" className={cx(inputClass, 'min-h-48 leading-relaxed')} value={fields.body} disabled={future}
          maxLength={100_000} placeholder="Write anything…" onChange={(e) => update({ body: e.target.value })} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Mood (optional)">
          <div className="flex flex-wrap items-center gap-1">
            <Segmented label="Mood" size="sm" value={fields.mood?.toString() ?? null} options={MOODS} onChange={(v) => update({ mood: Number(v) })} />
            {fields.mood !== null && <Button size="sm" variant="ghost" onClick={() => update({ mood: null })}>Clear</Button>}
          </div>
        </Field>
        <Field label="Energy (optional)">
          <div className="flex flex-wrap items-center gap-1">
            <Segmented label="Energy" size="sm" value={fields.energy?.toString() ?? null} options={ENERGY} onChange={(v) => update({ energy: Number(v) })} />
            {fields.energy !== null && <Button size="sm" variant="ghost" onClick={() => update({ energy: null })}>Clear</Button>}
          </div>
        </Field>
      </div>
      <details open={!!(fields.went_well || fields.was_difficult || fields.on_mind)}>
        <summary className="cursor-pointer text-sm font-medium">Reflection prompts (optional)</summary>
        <div className="mt-3 flex flex-col gap-3">
          <Field label="What went well?" htmlFor="j-well">
            <textarea id="j-well" className={inputClass} rows={2} value={fields.went_well} disabled={future} onChange={(e) => update({ went_well: e.target.value })} />
          </Field>
          <Field label="What was difficult?" htmlFor="j-hard">
            <textarea id="j-hard" className={inputClass} rows={2} value={fields.was_difficult} disabled={future} onChange={(e) => update({ was_difficult: e.target.value })} />
          </Field>
          <Field label="What is on your mind?" htmlFor="j-mind">
            <textarea id="j-mind" className={inputClass} rows={2} value={fields.on_mind} disabled={future} onChange={(e) => update({ on_mind: e.target.value })} />
          </Field>
        </div>
      </details>
      <JournalPrompts disabled={future} onInsert={(p) => update({ body: `${fieldsRef.current.body.trimEnd()}${fieldsRef.current.body.trim() ? '\n\n' : ''}${p}\n` })} />
    </Card>
  )
}

function SaveStatus({ status }: { status: Status }) {
  const map: Partial<Record<Status, [string, string]>> = {
    dirty: ['Unsaved changes', 'text-muted'],
    saving: ['Saving…', 'text-muted'],
    saved: ['Saved', 'text-accent'],
    error: ['Couldn’t save', 'text-danger'],
    conflict: ['Needs your decision', 'text-warn'],
  }
  const entry = map[status]
  return <span role="status" aria-live="polite" className={cx('text-sm font-medium', entry?.[1])}>{entry?.[0] ?? ''}</span>
}

function ConflictPanel({ mine, theirs, onKeepMine, onUseTheirs }: {
  mine: JournalFields; theirs: JournalEntry; onKeepMine: () => void; onUseTheirs: () => void
}) {
  const { settings } = useApp()
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-lg border border-warn/40 bg-warn-soft p-3 text-sm">
      <p className="font-medium text-warn">
        This entry was changed somewhere else (another tab or device){theirs.updated_at && ` at ${formatDateTime(theirs.updated_at, settings.timezone)}`}.
        Nothing has been overwritten. Choose which version to keep.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><p className="mb-1 font-medium">Your version (this screen)</p><pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-card p-2 font-sans">{mine.body || '(empty)'}</pre></div>
        <div><p className="mb-1 font-medium">Saved version</p><pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-card p-2 font-sans">{theirs.body || '(empty)'}</pre></div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" onClick={onKeepMine}>Keep my version</Button>
        <Button size="sm" onClick={onUseTheirs}>Use the saved version</Button>
        <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(mine.body)}>Copy my text</Button>
      </div>
    </div>
  )
}
