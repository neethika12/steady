// Shapes returned by the backend API (see backend/app/schemas.py).

export type ISODate = string // "YYYY-MM-DD", a local calendar day
export type Priority = 'low' | 'medium' | 'high'
export type ReviewOutcome = 'completed' | 'partial' | 'not_completed'
export type PlanState = ReviewOutcome | 'cancelled' | 'awaiting_review' | 'planned'
export type Reason =
  | 'not_enough_time' | 'too_large' | 'unclear_next_step' | 'waiting'
  | 'low_energy' | 'priority_changed' | 'forgot_distracted' | 'other'

export interface Settings {
  timezone: string
  timezone_confirmed: boolean
  week_start: number
  timeline_start: string // "HH:MM:SS"
  timeline_end: string // earlier than the start = the day runs past midnight
  currency: string // ISO code, e.g. USD
  today: ISODate
  now: string
}

export interface Task {
  id: string
  title: string
  description: string
  priority: Priority
  category: string | null
  estimated_minutes: number | null
  actual_minutes: number | null
  deadline: ISODate | null
  planned_date: ISODate | null
  status: 'active' | 'completed' | 'cancelled' | 'split'
  origin: 'inbox' | 'day' // where it was created (or explicitly moved)
  completed_at: string | null
  cancelled_at: string | null
  archived_at: string | null
  parent_task_id: string | null
  source_inbox_item_id: string | null
  created_at: string
  updated_at: string
}

export interface Plan {
  id: string
  task_id: string
  plan_date: ISODate
  planned_time: string | null // "HH:MM:SS" local start time; null = anytime
  planned_end_time: string | null // optional end of a time range
  outcome: ReviewOutcome | 'cancelled' | null
  state: PlanState
  reason: Reason | null
  reason_note: string | null
  reviewed_at: string | null
  completed_at: string | null
  follow_up: 'rescheduled' | 'split' | 'unscheduled' | 'cancelled' | 'left' | null
  carried_from_plan_id: string | null
  carried_from_date: ISODate | null
  carried_to_date: ISODate | null
  times_carried: number
  task: Task
}

export interface DayStats {
  date: ISODate
  planned: number
  counted: number
  completed: number
  partial: number
  not_completed: number
  awaiting_review: number
  open: number
  cancelled: number
  carried_in: number
  completion_pct: number | null
  estimated_minutes_planned: number
  estimated_minutes_completed: number
  effort_pct: number | null
  plans_without_estimate: number
}

export interface Day { date: ISODate; today: ISODate; stats: DayStats; plans: Plan[] }
export interface Week { start: ISODate; end: ISODate; today: ISODate; days: Day[] }

export interface AuditEntry {
  id: string
  entity_type: string
  action: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  note: string | null
  created_at: string
}

export interface TaskHistory { task: Task; plans: Plan[]; audit: AuditEntry[]; children: Task[] }

export type HabitKind = 'boolean' | 'duration' | 'count'
export type ScheduleType = 'daily' | 'weekdays' | 'weekly_target'

export interface ScheduleInput {
  schedule_type: ScheduleType
  weekdays: number[]
  weekly_target: number | null
  target_value: number
}

export interface Schedule extends ScheduleInput {
  id: string
  effective_from: ISODate
  effective_to: ISODate | null
}

export interface Habit {
  id: string
  name: string
  description: string
  kind: HabitKind
  unit: string | null
  start_date: ISODate
  archived_on: ISODate | null
  source_inbox_item_id: string | null
  current_schedule: Schedule | null
  schedules: Schedule[]
  pauses: { id: string; start_date: ISODate; end_date: ISODate | null }[]
  paused_today: boolean
}

export type HabitDayStatus =
  | 'inactive' | 'future' | 'paused' | 'done' | 'pending' | 'missed'
  | 'not_scheduled' | 'extra' | 'open'

export interface WeekProgress {
  week_start: ISODate
  week_end: ISODate
  sessions: number
  target: number
  required: number
  available_days: number
  met: boolean
  finished: boolean
}

export interface HabitDayItem {
  habit: Habit
  status: HabitDayStatus
  value: number | null
  target_value: number | null
  schedule_type: ScheduleType | null
  streak: { unit: 'days' | 'weeks'; value: number } | null
  week: WeekProgress | null
}

export interface HabitDay {
  date: ISODate
  today: ISODate
  scheduled: HabitDayItem[]
  weekly: HabitDayItem[]
  other: HabitDayItem[]
  progress: { done: number; scheduled: number; pct: number | null }
}

export interface HabitCalendarRow {
  habit: Habit
  days: { date: ISODate; status: HabitDayStatus; value: number | null }[]
}

export interface JournalFields {
  body: string
  mood: number | null
  energy: number | null
  went_well: string
  was_difficult: string
  on_mind: string
}

export interface JournalEntry extends JournalFields {
  entry_date: ISODate
  exists: boolean
  version: number
  updated_at: string | null
}

export interface JournalListItem {
  entry_date: ISODate
  snippet: string
  word_count: number
  mood: number | null
  energy: number | null
  updated_at: string
}

export interface TaskInsights {
  start: ISODate
  end: ISODate
  evaluated_through: ISODate
  totals: Record<string, number | null>
  days: DayStats[]
  reasons: {
    unfinished: number
    with_reason: number
    without_reason: number
    tagged: number
    untagged: number
    by_reason: { reason: Reason; label: string; count: number }[]
    records: { plan_id: string; date: ISODate; task_title: string; outcome: string; reason: Reason | null; note: string | null }[]
  }
  carryover: {
    carried_plans: number
    tasks_carried: number
    share_of_plans_pct: number | null
    most_carried: { task_id: string; title: string; times_carried: number }[]
  }
  durations: {
    tasks_with_both: number
    completed_without_actual: number
    estimated_total: number
    actual_total: number
    rows: { task_id: string; title: string; date: ISODate; estimated_minutes: number; actual_minutes: number }[]
  }
}

export interface HabitInsightRow {
  habit_id: string
  name: string
  archived: boolean
  scheduled_days: number
  completed_days: number
  missed_days: number
  pending_today: number
  paused_days: number
  extra_checkins: number
  consistency_pct: number | null
  weekly: { weeks_evaluated: number; weeks_met: number; sessions: number } | null
}

export interface HabitInsights {
  start: ISODate
  end: ISODate
  evaluated_through: ISODate
  habits: HabitInsightRow[]
  totals: { scheduled: number; completed: number; pct: number | null }
}

// ---------------------------------------------------------------- money

export type AccountType = 'debit' | 'credit'
export type MoneyKind = 'expense' | 'income' | 'payment'

export interface MoneyAccount {
  id: string
  name: string
  type: AccountType
  opening_balance_cents: number
  opened_on: ISODate
  archived: boolean
  balance_cents: number // debit: money in it; credit: amount owed
}

export interface MoneyOverview {
  set_up: boolean
  accounts: MoneyAccount[]
  available_cents: number
  owed_cents: number
  splitwise: MoneySplitwise
  net_cents: number // available - owed on cards + Splitwise get - Splitwise pay
}

/** Totals copied by hand from the Splitwise app. */
export interface MoneySplitwise { get_cents: number; pay_cents: number; updated_at: string | null }

export interface MoneyCategory { id: string; name: string; kind: 'expense' | 'income'; archived: boolean }

export interface MoneyEntry {
  id: string
  occurred_on: ISODate
  kind: MoneyKind
  amount_cents: number
  account_id: string
  account_name: string
  account_type: AccountType
  to_account_id: string | null
  to_account_name: string | null
  category_id: string | null
  category_name: string | null
  note: string
  recurring_id: string | null
  created_at: string
}

export type Frequency = 'weekly' | 'monthly' | 'yearly'

export interface MoneyRecurring {
  id: string
  name: string
  kind: MoneyKind
  amount_cents: number
  account_id: string
  account_name: string
  to_account_id: string | null
  to_account_name: string | null
  category_id: string | null
  category_name: string | null
  frequency: Frequency
  interval: number
  anchor_on: ISODate
  day_of_month: number
  weekday: number // 0 = Monday
  paused: boolean
  next_on: ISODate | null // null while paused
}

export interface MoneyRecurringSummary { rules: MoneyRecurring[]; bills_next_30_days_cents: number }

export interface MoneyDay {
  date: ISODate
  transactions: MoneyEntry[]
  spent_cents: number
  income_cents: number
  scheduled: MoneyRecurring[] // future days only: repeating entries that will be added that day
}

export interface MoneyMonth {
  month: string
  start: ISODate
  end: ISODate
  spent_cents: number
  income_cents: number
  card_payments_cents: number
  by_category: { category_id: string; name: string; spent_cents: number; share_pct: number | null }[]
  days_counted: number
  avg_per_day_cents: number | null
  previous_month_spent_cents: number
  top_expenses: MoneyEntry[]
}
