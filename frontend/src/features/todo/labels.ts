import type { PlanState, Priority, Reason } from '../../types'

export const REASONS: { value: Reason; label: string }[] = [
  { value: 'not_enough_time', label: 'Not enough time' },
  { value: 'too_large', label: 'Task was too large' },
  { value: 'unclear_next_step', label: 'Unclear next step' },
  { value: 'waiting', label: 'Waiting on something' },
  { value: 'low_energy', label: 'Low energy' },
  { value: 'priority_changed', label: 'Priority changed' },
  { value: 'forgot_distracted', label: 'Forgot or got distracted' },
  { value: 'other', label: 'Other' },
]
export const REASON_LABEL = Object.fromEntries(REASONS.map((r) => [r.value, r.label])) as Record<Reason, string>

export const STATE_LABEL: Record<PlanState, string> = {
  planned: 'Planned',
  awaiting_review: 'Not marked yet',
  completed: 'Completed',
  partial: 'Partly completed',
  not_completed: 'Not completed',
  cancelled: 'Cancelled',
}

export const PRIORITY_LABEL: Record<Priority, string> = { high: 'High', medium: 'Medium', low: 'Low' }

export const FOLLOW_UP_LABEL = {
  rescheduled: 'Rescheduled',
  split: 'Split into smaller tasks',
  unscheduled: 'Moved to the Inbox',
  left: 'Left on this day',
  cancelled: 'Cancelled',
} as const

export const CANCEL_EXPLANATION =
  'Cancelled tasks are listed separately and are not counted in that day’s completion percentage.'
