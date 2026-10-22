import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { get, put } from './api'
import { DateBar } from './components/DateBar'
import { HeroBanner } from './components/Motivation'
import { Button, ErrorNote, Loading, ToastProvider, cx } from './components/ui'
import { AppContext, type AppState, type TabId } from './context'
import { HabitsTab } from './features/habits/HabitsTab'
import { JournalTab } from './features/journal/JournalTab'
import { SettingsDialog } from './features/settings/SettingsDialog'
import { TaskInbox } from './features/todo/TaskInbox'
import { TodoTab } from './features/todo/TodoTab'
import { CalendarTab } from './features/calendar/CalendarTab'
import { MoneyTab } from './features/money/MoneyTab'
import { AccountMenu, AuthGate, RecoveryReminder } from './features/account/Auth'
import { useLoad } from './hooks'
import type { Settings } from './types'

const TABS: { id: TabId; label: string; short: string }[] = [
  { id: 'todo', label: 'To-Do', short: 'To-Do' },
  { id: 'calendar', label: 'Calendar', short: 'Calendar' },
  { id: 'habits', label: 'Habit Tracker', short: 'Habits' },
  { id: 'journal', label: 'Journal', short: 'Journal' },
  { id: 'money', label: 'Money', short: 'Money' },
]

function tabFromHash(): TabId {
  const h = window.location.hash.replace('#', '')
  return (TABS.find((t) => t.id === h)?.id ?? 'todo')
}

function readStoredDate(): string | null {
  try { return sessionStorage.getItem('steady.date') } catch { return null }
}

export default function App() {
  return (
    <ToastProvider>
      <AuthGate>
        <Shell />
      </AuthGate>
    </ToastProvider>
  )
}

function Shell() {
  const settings = useLoad<Settings>((s) => get('/settings', s), 'settings')
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [date, setDateState] = useState<string | null>(readStoredDate)
  const [showSettings, setShowSettings] = useState(false)
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Keep "today" fresh if the app stays open past midnight.
  useEffect(() => {
    const refresh = () => settings.reload()
    const timer = setInterval(refresh, 5 * 60_000)
    window.addEventListener('focus', refresh)
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [settings.reload])

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const goToTab = useCallback((t: TabId) => {
    setTab(t)
    history.replaceState(null, '', `#${t}`)
  }, [])

  const setDate = useCallback((d: string) => {
    setDateState(d)
    try { sessionStorage.setItem('steady.date', d) } catch { /* storage unavailable */ }
  }, [])

  const s = settings.data
  const value: AppState | null = useMemo(() => s && {
    settings: s,
    today: s.today,
    date: date ?? s.today,
    setDate,
    reloadSettings: settings.reload,
    goToTab,
  }, [s, date, setDate, settings.reload, goToTab])

  if (!value) {
    return (
      <main className="mx-auto max-w-xl p-6">
        {settings.error ? (
          <ErrorNote message={`Steady couldn't load: ${settings.error}`} onRetry={settings.reload} />
        ) : <Loading label="Starting Steady…" />}
      </main>
    )
  }

  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    let next = i + delta
    if (e.key === 'Home') next = 0
    if (e.key === 'End') next = TABS.length - 1
    if (next === i && !delta) return
    e.preventDefault()
    next = (next + TABS.length) % TABS.length
    goToTab(TABS[next].id)
    tabRefs.current[next]?.focus()
  }

  return (
    <AppContext.Provider value={value}>
      <div className="flex min-h-dvh flex-col lg:flex-row">
      <div className="min-w-0 flex-1">
      <div className="mx-auto flex max-w-6xl flex-col px-3 pb-28 sm:px-6 sm:pb-16">
        <header className="flex items-center gap-3 py-4">
          <span aria-hidden className="grid size-8 place-items-center rounded-lg bg-ink text-sm font-bold text-white">S</span>
          <h1 className="text-xl font-semibold tracking-tight">Steady</h1>
          <span className="hidden text-sm text-muted sm:inline">Plan your days. Build habits. Reflect.</span>
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setShowSettings(true)}>Settings</Button>
          <AccountMenu />
        </header>

        <RecoveryReminder />
        <HeroBanner />

        {!value.settings.timezone_confirmed && <TimezoneBanner settings={value.settings} onDone={settings.reload} />}

        {/* Phones: a tab bar fixed to the bottom of the screen (like an app). Larger screens: sticky at the top. */}
        <nav role="tablist" aria-label="Sections"
          className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card/95 px-1 pb-[max(0.25rem,env(safe-area-inset-bottom))] pt-1 backdrop-blur sm:sticky sm:top-0 sm:bottom-auto sm:z-10 sm:mb-5 sm:border-0 sm:bg-paper/90 sm:px-0 sm:py-2">
          <div className="flex gap-0.5 sm:inline-flex sm:gap-1 sm:rounded-xl sm:bg-card sm:p-1 sm:shadow-sm sm:ring-1 sm:ring-line">
            {TABS.map((t, i) => (
              <button
                key={t.id}
                ref={(el) => { tabRefs.current[i] = el }}
                role="tab"
                id={`tab-${t.id}`}
                aria-selected={tab === t.id}
                aria-controls={`panel-${t.id}`}
                tabIndex={tab === t.id ? 0 : -1}
                onClick={() => goToTab(t.id)}
                onKeyDown={(e) => onTabKey(e, i)}
                className={cx('flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 whitespace-nowrap rounded-lg px-1 py-1.5 text-[11px] font-semibold transition-colors sm:flex-none sm:flex-row sm:gap-2 sm:px-5 sm:py-2.5 sm:text-[15px]',
                  tab === t.id ? 'text-accent sm:bg-accent sm:text-white sm:shadow-sm' : 'text-ink/60 hover:text-accent sm:text-ink/70 sm:hover:bg-accent-soft')}
              >
                <TabIcon id={t.id} />
                <span className="sm:hidden">{t.short}</span>
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            ))}
          </div>
        </nav>

        <main id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="flex flex-col gap-4">
          {tab !== 'todo' && <DateBar />}
          {tab === 'todo' && <TodoTab />}
          {tab === 'calendar' && <CalendarTab />}
          {tab === 'habits' && <HabitsTab />}
          {tab === 'journal' && <JournalTab />}
          {tab === 'money' && <MoneyTab />}
        </main>
      </div>
      </div>
      <div className="hidden lg:contents"><TaskInbox /></div>
      </div>
      {showSettings && <SettingsDialog onClose={() => setShowSettings(false)} />}
    </AppContext.Provider>
  )
}

function TimezoneBanner({ settings, onDone }: { settings: Settings; onDone: () => void }) {
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [pending, setPending] = useState(false)
  const save = async (body: object) => {
    setPending(true)
    try { await put('/settings', body); onDone() } finally { setPending(false) }
  }
  return (
    <div role="region" aria-label="Timezone" className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-card px-4 py-3 text-sm">
      <span className="flex-1">
        Calendar days follow <strong>{settings.timezone}</strong>.
        {browserTz && browserTz !== settings.timezone && <> This device reports <strong>{browserTz}</strong>.</>}
      </span>
      {browserTz && browserTz !== settings.timezone && (
        <Button size="sm" variant="primary" pending={pending} onClick={() => save({ timezone: browserTz })}>Use {browserTz}</Button>
      )}
      <Button size="sm" pending={pending} onClick={() => save({ timezone_confirmed: true })}>Keep {settings.timezone}</Button>
    </div>
  )
}

/** Simple line icons for the section tabs. */
function TabIcon({ id }: { id: TabId }) {
  const common = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
    strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }
  if (id === 'todo') {
    return <svg {...common}><rect x="3" y="3" width="18" height="18" rx="4" /><path d="m8 12 3 3 5-6" /></svg>
  }
  if (id === 'money') {
    return <svg {...common}><rect x="2" y="6" width="20" height="13" rx="3" /><path d="M2 10h20" /><path d="M16 15h2" /></svg>
  }
  if (id === 'calendar') {
    return <svg {...common}><rect x="3" y="4" width="18" height="17" rx="3" /><path d="M3 9h18M8 2v4M16 2v4" /><path d="M12 13v3l2 1" /></svg>
  }
  if (id === 'habits') {
    return <svg {...common}><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 4v5h-5" /></svg>
  }
  return <svg {...common}><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 21.5V4.5" /><path d="M9 7h7M9 11h5" /></svg>
}
