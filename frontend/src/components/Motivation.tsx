// Quiet encouragement: a daily affirmation, a greeting, and progress messages.
// Wording is supportive and never judges unfinished work.

import { useState } from 'react'
import { useApp } from '../context'
import { formatLong } from '../dates'
import { Button } from './ui'

export const AFFIRMATIONS = [
  'Small steps still move you forward.',
  'You are allowed to go at your own pace.',
  'Progress, not perfection.',
  'Today is a good day to begin again.',
  'You have handled hard things before. You can handle this.',
  'Rest is part of the plan, not a break from it.',
  'One task at a time is enough.',
  'Your effort matters, even when no one sees it.',
  'Done is better than perfect.',
  'You are building something, one day at a time.',
  'Focus on what you can do right now.',
  'Be proud of how far you have come.',
  'Every small win counts.',
  'You don’t have to do it all. Just do the next thing.',
  'Consistency beats intensity.',
  'Your future self will thank you for today’s effort.',
  'Mistakes are proof that you are trying.',
  'Start where you are. Use what you have.',
  'Keep showing up. That is the whole secret.',
  'You are capable of more than you think.',
  'Be patient with yourself while you grow.',
  'A calm mind gets more done.',
  'Clarity comes from action, not from waiting.',
  'Small habits, compounded, become big changes.',
  'You get to choose your next step.',
  'Asking for help is a strength.',
  'Energy follows attention.',
  'Make today count, in whatever way works for you.',
  'You’re doing better than you think.',
  'Discipline is remembering what you want.',
]

const COMPLETED = ['Task completed', 'Done. Nicely handled.', 'Completed. One step forward.', 'Done. Keep the momentum.']
const NOT_DONE = ['Saved. Tomorrow is a fresh start.', 'Saved. Be kind to yourself.', 'Noted. Every day is a new chance.']
const HABIT_DONE = ['Check-in saved', 'Check-in saved. Consistency builds.', 'Logged. Keep it going.']

const pick = (list: string[]) => list[Math.floor(Math.random() * list.length)]
export const completedMessage = () => pick(COMPLETED)
export const notDoneMessage = () => pick(NOT_DONE)
export const habitMessage = () => pick(HABIT_DONE)

/** Short, calm line for the day's progress. */
export function progressMessage(pct: number | null, planned: number, when: 'past' | 'today' | 'future'): string {
  if (!planned || pct === null) {
    if (when === 'today') return 'A clear day. Pick one small task to begin.'
    return when === 'future' ? 'Nothing planned yet.' : 'Nothing was planned for this day.'
  }
  if (pct >= 100) return 'All planned tasks complete. Well done.'
  if (pct >= 50) return 'Over halfway. Strong progress.'
  if (pct > 0) return 'Good start. Keep the momentum.'
  if (when === 'future') return 'Planned ahead.'
  return when === 'today' ? 'One task at a time. You’ve got this.' : 'This day is a record, not a verdict.'
}

function dayIndex(iso: string) {
  return Math.floor(Date.parse(`${iso}T00:00:00Z`) / 86_400_000)
}

function greeting(timezone: string) {
  const h = Number(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hourCycle: 'h23', timeZone: timezone }).format(new Date()))
  if (h < 5) return 'Good evening'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

/** Greeting + today's affirmation (the same all day; "New quote" shows the next). */
export function HeroBanner() {
  const { today, settings } = useApp()
  const [offset, setOffset] = useState(0)
  const affirmation = AFFIRMATIONS[(dayIndex(today) + offset) % AFFIRMATIONS.length]
  return (
    <section aria-label="Daily affirmation"
      className="relative mb-5 overflow-hidden rounded-2xl bg-night px-6 py-5 text-white shadow-sm">
      <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-1/2 bg-linear-to-l from-accent/35 to-transparent" />
      <div className="relative flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">
            {greeting(settings.timezone)} · {formatLong(today)}
          </p>
          <p key={affirmation} className="mt-2 animate-fade font-serif text-2xl leading-snug italic text-white sm:text-[1.7rem]">
            {affirmation}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-[0.14em] text-white/45">Today’s focus</span>
          <Button size="xs" className="border-white/25 bg-white/5 text-white/85 hover:bg-white/15 hover:text-white"
            onClick={() => setOffset((o) => o + 1)}>New quote</Button>
        </div>
      </div>
    </section>
  )
}

/** Circular progress for the day. */
export function ProgressRing({ pct, size = 64 }: { pct: number | null; size?: number }) {
  const r = (size - 8) / 2
  const c = 2 * Math.PI * r
  const value = Math.max(0, Math.min(100, pct ?? 0))
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={pct === null ? 'No progress yet' : `${value}% complete`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-line)" strokeWidth="6" />
      {value > 0 && <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-accent)" strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${(value / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dasharray 0.6s ease' }} />}
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-ink text-[13px] font-semibold">
        {pct === null ? '–' : `${value}%`}
      </text>
    </svg>
  )
}
