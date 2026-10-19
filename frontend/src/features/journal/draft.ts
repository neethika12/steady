// Local, recoverable drafts. Kept in this browser only until the server confirms a save.
import type { JournalFields } from '../../types'

export interface Draft { fields: JournalFields; baseVersion: number; savedAt: string }

// Drafts are kept per account, and removed when that account logs out (shared computers).
const PREFIX = 'steady.journal.draft.'
let owner = 'anonymous'
export function setDraftOwner(userId: string) { owner = userId }

const key = (date: string) => `${PREFIX}${owner}.${date}`

export function clearDraftsOf(userId: string) {
  try {
    const mine = Object.keys(localStorage).filter((k) => k.startsWith(`${PREFIX}${userId}.`) || /^steady\.journal\.draft\.\d{4}-/.test(k))
    mine.forEach((k) => localStorage.removeItem(k))
  } catch { /* storage unavailable */ }
}

export function readDraft(date: string): Draft | null {
  try {
    const raw = localStorage.getItem(key(date))
    return raw ? (JSON.parse(raw) as Draft) : null
  } catch {
    return null
  }
}

export function writeDraft(date: string, fields: JournalFields, baseVersion: number) {
  try {
    localStorage.setItem(key(date), JSON.stringify({ fields, baseVersion, savedAt: new Date().toISOString() }))
  } catch { /* storage full or disabled: the editor still shows the text */ }
}

export function clearDraft(date: string) {
  try { localStorage.removeItem(key(date)) } catch { /* ignore */ }
}

export const FIELD_KEYS: (keyof JournalFields)[] = ['body', 'mood', 'energy', 'went_well', 'was_difficult', 'on_mind']

export function sameFields(a: JournalFields, b: JournalFields): boolean {
  return FIELD_KEYS.every((k) => a[k] === b[k])
}

export function pickFields(e: JournalFields): JournalFields {
  return { body: e.body, mood: e.mood, energy: e.energy, went_well: e.went_well, was_difficult: e.was_difficult, on_mind: e.on_mind }
}
