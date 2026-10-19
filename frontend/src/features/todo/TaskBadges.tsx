import { Badge } from '../../components/ui'
import { formatMinutes, formatShort } from '../../dates'
import type { Plan, Task } from '../../types'
import { PRIORITY_LABEL } from './labels'

export function TaskBadges({ task, plan, today }: { task: Task; plan?: Plan; today: string }) {
  const overdue = task.deadline && task.deadline < today && task.status === 'active'
  return (
    <div className="flex flex-wrap items-center gap-1">
      {task.priority !== 'medium' && <Badge tone={task.priority === 'high' ? 'warn' : 'neutral'}>{PRIORITY_LABEL[task.priority]} priority</Badge>}
      {task.category && <Badge>{task.category}</Badge>}
      {task.estimated_minutes && <Badge title="Estimated duration">~{formatMinutes(task.estimated_minutes)}</Badge>}
      {task.actual_minutes !== null && <Badge title="Actual duration">took {formatMinutes(task.actual_minutes)}</Badge>}
      {task.deadline && <Badge tone={overdue ? 'danger' : 'neutral'}>Due {formatShort(task.deadline)}</Badge>}
      {plan?.carried_from_date && (
        <Badge tone="accent" title={`Carried forward ${plan.times_carried} time(s)`}>
          Carried from {formatShort(plan.carried_from_date)}{plan.times_carried > 1 ? ` · ${plan.times_carried}×` : ''}
        </Badge>
      )}
      {plan?.carried_to_date && <Badge title="This day's record is kept; the task continues on a later day">Moved on to {formatShort(plan.carried_to_date)}</Badge>}
    </div>
  )
}
