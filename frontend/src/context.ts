import { createContext, useContext } from 'react'
import type { ISODate, Settings } from './types'

export interface AppState {
  settings: Settings
  today: ISODate
  date: ISODate // the shared selected day (To-Do, Habits, Journal)
  setDate: (d: ISODate) => void
  reloadSettings: () => void
  goToTab: (tab: TabId) => void
}

export type TabId = 'todo' | 'calendar' | 'habits' | 'journal' | 'money'

export const AppContext = createContext<AppState | null>(null)

export function useApp(): AppState {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp outside AppContext')
  return ctx
}
