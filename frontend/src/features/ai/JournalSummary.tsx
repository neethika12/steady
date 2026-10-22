import { useState } from 'react'
import { get, post } from '../../api'
import { Button, Card, ErrorNote, Spinner } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort } from '../../dates'
import { useAction, useLoad } from '../../hooks'
import type { JournalListItem } from '../../types'
import { AiError, AiLabel, useAiEnabled, useAiStatus, useAiWords } from './AiStatus'
import { useAiRequest } from './useAiRequest'

interface Preview {
  entries: { date: string; exists: boolean; characters: number; truncated: boolean }[]
  fields_sent: string[]; not_sent: string[]; destination: string
}
interface Result { summary: string; themes: { text: string; dates: string[] }[] }

/** Journal analysis is only ever run on entries you pick, after you see what will be shared. */
export function JournalSummary() {
  const { today } = useApp()
  const [open, setOpen] = useState(false)
  const list = useLoad<JournalListItem[]>((s) => (open ? get('/journal', s) : Promise.resolve([])), `js-${open}-${today}`)
  const [chosen, setChosen] = useState<string[]>([])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [agreed, setAgreed] = useState(false)
  const loadPreview = useAction()
  const ai = useAiRequest<Result>()
  const { status } = useAiStatus()
  const words = useAiWords()

  const toggle = (d: string) => {
    setPreview(null); setAgreed(false); ai.reset()
    setChosen((c) => (c.includes(d) ? c.filter((x) => x !== d) : c.length >= 14 ? c : [...c, d]))
  }

  const enabled = useAiEnabled()
  if (!enabled) return null
  return (
    <Card aria-label="Summarise entries">
      <h3 className="font-semibold">Summarise entries (optional)</h3>
      <p className="mt-1 text-sm text-muted">Journal text is never sent anywhere unless you choose entries here and confirm.</p>
      {!open ? <Button size="sm" className="mt-2" onClick={() => setOpen(true)}>Choose entries…</Button> : (
        <div className="mt-3 flex flex-col gap-3 text-sm">
          {list.error && <ErrorNote message={list.error} />}
          {list.data?.length === 0 && <p className="text-muted">No recent entries.</p>}
          <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto">
            {list.data?.map((e) => (
              <li key={e.entry_date}><label className="flex items-center gap-2">
                <input type="checkbox" className="size-4 accent-accent" checked={chosen.includes(e.entry_date)} onChange={() => toggle(e.entry_date)} />
                {formatShort(e.entry_date)} <span className="truncate text-muted">{e.snippet}</span>
              </label></li>
            ))}
          </ul>
          {chosen.length > 0 && !preview && (
            <Button size="sm" pending={loadPreview.pending} onClick={async () => {
              const p = await loadPreview.run(() => get<Preview>(`/ai/journal-summary/preview?${chosen.map((d) => `dates=${d}`).join('&')}`))
              if (p) setPreview(p)
            }}>Show what will be shared</Button>
          )}
          {preview && !ai.data && (
            <div className="rounded-lg border border-line bg-paper p-3">
              <p className="font-medium">This will be sent to {preview.destination}:</p>
              <ul className="mt-1 list-inside list-disc">
                {preview.entries.filter((e) => e.exists).map((e) => (
                  <li key={e.date}>{formatShort(e.date)}: about {e.characters} characters{e.truncated && ' (shortened)'}</li>
                ))}
              </ul>
              <p className="mt-1">Fields: {preview.fields_sent.join(', ')}. Not sent: {preview.not_sent.join(', ')}.</p>
              <p className="mt-1 text-muted">{words.hosted ? 'Groq doesn’t keep or train on it, and the result is not saved.' : 'It stays on this computer and the result is not saved.'}</p>
              <label className="mt-2 flex items-center gap-2">
                <input type="checkbox" className="size-4 accent-accent" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
                I want to share these entries with {words.hosted ? 'Groq’s AI service' : 'the local model'}
              </label>
              <Button size="sm" variant="primary" className="mt-2" disabled={!agreed} pending={ai.pending}
                onClick={() => ai.run(() => post<Result>('/ai/journal-summary', { dates: chosen, confirm_share: true }))}>Summarise</Button>
            </div>
          )}
          {ai.pending && <Spinner label={words.thinking} />}
          {ai.error !== null && <AiError error={ai.error} />}
          {ai.data && (
            <div className="flex flex-col gap-2">
              <AiLabel model={status?.model} />
              <p>{ai.data.summary}</p>
              {ai.data.themes.length > 0 && (
                <ul className="list-inside list-disc">
                  {ai.data.themes.map((t) => <li key={t.text}>{t.text} <span className="text-muted">({t.dates.map(formatShort).join(', ')})</span></li>)}
                </ul>
              )}
              <div><Button size="sm" variant="ghost" onClick={() => { ai.reset(); setPreview(null); setAgreed(false) }}>Clear</Button></div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
