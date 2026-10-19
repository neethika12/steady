// Calendar-date helpers that work on "YYYY-MM-DD" strings.
// Dates are handled as plain calendar days (UTC internally), so the browser's
// own timezone never shifts them. "Today" always comes from the backend,
// which uses the timezone chosen in Settings.

import type { ISODate } from './types'

function parts(iso: ISODate): [number, number, number] {
  const [y, m, d] = iso.split('-').map(Number)
  return [y, m, d]
}

function toDate(iso: ISODate): Date {
  const [y, m, d] = parts(iso)
  return new Date(Date.UTC(y, m - 1, d))
}

export function addDays(iso: ISODate, n: number): ISODate {
  const dt = toDate(iso)
  dt.setUTCDate(dt.getUTCDate() + n)
  return dt.toISOString().slice(0, 10)
}

/** 0 = Monday ... 6 = Sunday (same as the backend). */
export function weekdayIndex(iso: ISODate): number {
  return (toDate(iso).getUTCDay() + 6) % 7
}

export function weekStart(iso: ISODate, start: number): ISODate {
  return addDays(iso, -((weekdayIndex(iso) - start + 7) % 7))
}

export function weekDays(iso: ISODate, start: number): ISODate[] {
  const first = weekStart(iso, start)
  return Array.from({ length: 7 }, (_, i) => addDays(first, i))
}

export function daysBetween(a: ISODate, b: ISODate): number {
  return Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86_400_000)
}

const fmt = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(undefined, { ...opts, timeZone: 'UTC' })
const longFmt = fmt({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
const shortFmt = fmt({ weekday: 'short', day: 'numeric', month: 'short' })
const dayFmt = fmt({ weekday: 'short' })
const monthFmt = fmt({ month: 'long', year: 'numeric' })
const dayMonthFmt = fmt({ day: 'numeric', month: 'short' })

export const formatLong = (iso: ISODate) => longFmt.format(toDate(iso))
export const formatShort = (iso: ISODate) => shortFmt.format(toDate(iso))
export const formatWeekday = (iso: ISODate) => dayFmt.format(toDate(iso))
export const formatDayMonth = (iso: ISODate) => dayMonthFmt.format(toDate(iso))
export const formatMonth = (iso: ISODate) => monthFmt.format(toDate(iso))
export const dayOfMonth = (iso: ISODate) => parts(iso)[2]

export const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export const WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** "Today", "Yesterday", "Tomorrow" or a short date. */
export function relativeLabel(iso: ISODate, today: ISODate): string {
  const diff = daysBetween(today, iso)
  if (diff === 0) return 'Today'
  if (diff === -1) return 'Yesterday'
  if (diff === 1) return 'Tomorrow'
  return formatShort(iso)
}

export function formatMinutes(min: number | null | undefined): string {
  if (min === null || min === undefined) return '—'
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m ? `${h} h ${m} min` : `${h} h`
}

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' })

/** "HH:MM[:SS]" time of day → localised "9:30 AM" / "09:30". */
export function formatTime(t: string | null | undefined): string {
  if (!t) return 'Anytime'
  const [h, m] = t.split(':').map(Number)
  return timeFmt.format(new Date(Date.UTC(2000, 0, 1, h, m)))
}

/** Local clock time of an instant, e.g. "3:42 PM", in the configured timezone. */
export function formatClock(isoInstant: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZone: timezone }).format(new Date(isoInstant))
}

export const toMinutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5))
export const toHHMM = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`

/** The user's timeline in minutes. When it runs past midnight, `end` is beyond 1440. */
export function timelineSpan(s: { timeline_start: string; timeline_end: string }) {
  const start = toMinutes(s.timeline_start)
  const endRaw = toMinutes(s.timeline_end)
  const pastMidnight = endRaw < start
  return { start, end: pastMidnight ? endRaw + 1440 : endRaw, endRaw, pastMidnight }
}

/** "9:00 AM – 10:30 AM", "9:00 AM" or "Anytime". */
export function formatTimeRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start) return 'Anytime'
  return end ? `${formatTime(start)} – ${formatTime(end)}` : formatTime(start)
}

export function formatDateTime(isoInstant: string, timezone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium', timeStyle: 'short', timeZone: timezone,
  }).format(new Date(isoInstant))
}
