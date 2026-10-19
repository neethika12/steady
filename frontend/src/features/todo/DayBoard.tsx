import { useEffect, useRef, useState } from 'react'
import { patch, put } from '../../api'
import { describeTimeline, TimelineHoursDialog } from '../../components/TimelineHours'
import { Button, Dialog, ErrorNote, cx, useToast } from '../../components/ui'
import { useApp } from '../../context'
import { formatMinutes, formatShort, formatTime, formatTimeRange, timelineSpan, toHHMM, toMinutes } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import type { Plan } from '../../types'
import { CANCEL_EXPLANATION, REASON_LABEL } from './labels'
import { PlanRow } from './PlanRow'
import { TaskFormDialog } from './TaskForm'
import { TASK_DRAG_TYPE, rangeMinutes, setTaskDragData, useDropToDay } from './dropToDay'

const HOUR_PX = 64 // height of one hour on the timeline
const PX = HOUR_PX / 60

type Sheet = { id: string; askReason: boolean }

const PRIORITY_GROUPS = [
  { key: 'high', label: 'High priority', short: 'High', dot: 'bg-danger', bg: 'bg-[#fdeeee]', ring: 'ring-[#f5c9c9]', head: 'text-danger' },
  { key: 'medium', label: 'Medium priority', short: 'Medium', dot: 'bg-sun', bg: 'bg-[#fdf3e3]', ring: 'ring-[#f3dcb6]', head: 'text-warn' },
  { key: 'low', label: 'Low priority', short: 'Low', dot: 'bg-teal', bg: 'bg-[#e9f5f2]', ring: 'ring-[#c6e5de]', head: 'text-teal' },
] as const
type PriorityGroup = (typeof PRIORITY_GROUPS)[number]

/** One priority column. Dropping a task here plans it for this day with this priority. */
function PriorityColumn({ group, date, plans, onOpen, onChanged }: {
  group: PriorityGroup; date: string; plans: Plan[]; onOpen: (p: Plan, askReason?: boolean) => void; onChanged: () => void
}) {
  const [over, setOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const toast = useToast()
  const accepts = (e: React.DragEvent) => e.dataTransfer.types.includes(TASK_DRAG_TYPE)
  // Clicking the column's free space (not a task) opens "New task" with this priority.
  const onBackgroundClick = (e: React.MouseEvent) => {
    if (!(e.target as HTMLElement).closest('li, button, a, input, textarea, dialog, [role="alert"]')) setCreating(true)
  }
  const onDrop = async (e: React.DragEvent) => {
    if (!accepts(e)) return
    e.preventDefault()
    e.stopPropagation()
    setOver(false)
    setError(null)
    const id = e.dataTransfer.getData(TASK_DRAG_TYPE)
    try {
      await put(`/tasks/${id}/schedule`, { planned_date: date }) // no-op if it's already on this day
      await patch(`/tasks/${id}`, { priority: group.key })
      toast(`Moved to ${group.short} priority`)
      notifyChanged('tasks')
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    }
  }
  return (
    <section aria-label={group.label}
      onDragOver={(e) => { if (!accepts(e)) return; e.preventDefault(); e.stopPropagation(); setOver(true) }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false) }}
      onDrop={onDrop}
      onClick={onBackgroundClick}
      className={cx('flex min-h-24 min-w-0 cursor-pointer flex-col rounded-xl p-2 ring-1 transition @3xl:min-h-40', group.bg, group.ring,
        over && 'ring-2 ring-accent')}>
      <h4 className={cx('flex items-center gap-2 px-2 pb-2 pt-1 text-sm font-semibold', group.head)}>
        <span aria-hidden className={cx('size-2.5 rounded-full', group.dot)} />
        {group.short}
        <span className="ml-auto rounded-full bg-white/70 px-2 text-xs font-medium text-muted">{plans.length}</span>
      </h4>
      {error && <ErrorNote message={error} />}
      {plans.length === 0 ? (
        <p className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-black/10 px-3 py-6 text-center text-xs text-muted">
          {over ? 'Drop to make it ' + group.short.toLowerCase() + ' priority' : 'No tasks. Click to add one.'}
        </p>
      ) : (
        <ul className="flex cursor-default flex-col gap-1.5">
          {plans.map((p) => <TaskItem key={p.id} plan={p} onOpen={onOpen} onChanged={onChanged} showTime hidePriority card />)}
        </ul>
      )}
      <button type="button" onClick={() => setCreating(true)} aria-label={`Add ${group.short.toLowerCase()} priority task`}
        className="mt-2 rounded-lg px-2 py-1.5 text-left text-xs font-medium text-muted transition hover:bg-white/60 hover:text-ink">
        + Add task
      </button>
      {creating && (
        <TaskFormDialog plannedDate={date} initialPriority={group.key} onClose={() => setCreating(false)} onSaved={onChanged} />
      )}
    </section>
  )
}

/** Day view: a clean list of Anytime tasks beside a calendar-style timeline. */
/**
 * The day's tasks, shown two ways:
 *   mode="list"     (To-Do tab)    one clean list: timed tasks in time order, then anytime tasks
 *   mode="calendar" (Calendar tab) only the timed tasks, on a calendar-style timeline
 */
export function DayBoard({ date, plans, onChanged, mode }: {
  date: string; plans: Plan[]; onChanged: () => void; mode: 'list' | 'calendar'
}) {
  const drop = useDropToDay(onChanged)
  const [sheet, setSheet] = useState<Sheet | null>(null)
  const { settings } = useApp()
  const span = timelineSpan(settings)
  const dayPos = (t: string) => { const m = toMinutes(t); return span.pastMidnight && m < span.endRaw ? m + 1440 : m }
  const live = plans.filter((p) => p.state !== 'cancelled')
  const cancelled = plans.filter((p) => p.state === 'cancelled')
  const anytime = live.filter((p) => !p.planned_time).sort((a, b) => Number(!isOpen(a)) - Number(!isOpen(b)))
  const timed = live.filter((p) => p.planned_time)
  const listed = [...timed.sort((a, b) => dayPos(a.planned_time!) - dayPos(b.planned_time!)), ...anytime]
  const open = (plan: Plan, askReason = false) => setSheet({ id: plan.id, askReason })
  const sheetPlan = sheet ? plans.find((p) => p.id === sheet.id) : undefined

  return (
    <div className="@container flex flex-col gap-4">
      {drop.error && <ErrorNote message={drop.error} />}
      {mode === 'list' ? (
        <section {...drop.bind(date, 'keep')} aria-label="Day tasks"
          className={cx('flex min-w-0 flex-col rounded-xl border bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-colors',
            drop.isOver(date, 'keep') ? 'border-accent ring-2 ring-accent/20' : 'border-line')}>
          <header className="flex items-baseline gap-2 border-b border-line px-4 py-3">
            <h3 className="font-semibold">Tasks</h3>
            <span className="text-xs text-muted">{listed.length}</span>
            <span className="ml-auto text-xs text-muted">Timed tasks also appear in Calendar.</span>
          </header>
          {listed.length === 0 && (
            <p className="px-4 pt-4 text-center text-sm text-muted">No tasks for this day yet. Add one, or drag one in from the Inbox.</p>
          )}
          <div className="grid gap-3 p-3 @3xl:grid-cols-3">
            {PRIORITY_GROUPS.map((g) => (
              <PriorityColumn key={g.key} group={g} date={date} plans={listed.filter((p) => p.task.priority === g.key)}
                onOpen={open} onChanged={onChanged} />
            ))}
          </div>
        </section>
      ) : (
        // The Calendar tab shows only tasks planned at a time; anytime tasks live in the To-Do list.
        <Calendar date={date} timed={timed} drop={drop} onOpen={open} onChanged={onChanged} />
      )}

      {cancelled.length > 0 && (
        <details className="rounded-xl border border-line bg-card px-4 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-muted">Cancelled · {cancelled.length}</summary>
          <p className="my-2 text-xs text-muted">{CANCEL_EXPLANATION}</p>
          <ul className="flex flex-col gap-2 pb-2">
            {cancelled.map((p) => <PlanRow key={p.id} plan={p} onChanged={onChanged} />)}
          </ul>
        </details>
      )}

      {sheet && sheetPlan && (
        <Dialog title={sheetPlan.task.title} onClose={() => setSheet(null)} wide>
          <ul><PlanRow plan={sheetPlan} onChanged={onChanged} startAskingReason={sheet.askReason} expanded /></ul>
        </Dialog>
      )}
    </div>
  )
}

function isOpen(p: Plan) {
  return p.state === 'planned' || p.state === 'awaiting_review'
}

/** Complete / undo straight from a list item or a timeline block. */
type QuickMark = ReturnType<typeof useQuickMark>

/**
 * Complete / undo straight from a card or a timeline block. On "complete" the card shows
 * its finished state at once (`celebrating`) and plays a short animation; the list reloads
 * only after it ends, so nothing jumps mid-animation.
 */
function useQuickMark(plan: Plan, onChanged: () => void) {
  const action = useAction()
  const toast = useToast()
  const [celebrating, setCelebrating] = useState(false)
  const mark = async (outcome: 'completed' | null) => {
    if (outcome) setCelebrating(true)
    const r = await action.run(() => put(`/plans/${plan.id}/review`, {
      outcome, correction_note: outcome ? null : 'Undone in the day view',
    }))
    if (r === undefined) { setCelebrating(false); return }
    if (!outcome) toast('Undone') // completing is confirmed by the animation instead
    const refresh = () => { notifyChanged('tasks'); onChanged() }
    if (outcome) {
      setTimeout(refresh, 750)
      setTimeout(() => setCelebrating(false), 1600)
    } else refresh()
  }
  return { mark, pending: action.pending, error: action.error, celebrating }
}

function CheckIcon({ animate }: { animate: boolean }) {
  return (
    <svg viewBox="0 0 20 20" className="size-[70%]" aria-hidden>
      <path d="M5 10.5l3.2 3.2L15 7" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"
        strokeDasharray={16} className={animate ? 'animate-check-draw' : undefined} />
    </svg>
  )
}

/** The round check: empty = to do, filled with a tick = completed, red ✕ = not completed. */
function CheckCircle({ plan, quick, onOpen, small = false }: {
  plan: Plan; quick: QuickMark; onOpen: (p: Plan, askReason?: boolean) => void; small?: boolean
}) {
  const { today } = useApp()
  const { mark, pending, celebrating } = quick
  const title = plan.task.title
  const size = small ? 'size-4' : 'size-5'
  if (plan.state === 'completed' || celebrating) {
    return (
      <span className={cx('relative grid shrink-0 place-items-center', size)}>
        {celebrating && <span aria-hidden className="absolute inset-0 animate-check-ring rounded-full bg-accent opacity-0" />}
        <button type="button" disabled={pending || celebrating} onClick={() => mark(null)} aria-label={`Undo completion: ${title}`}
          className={cx(size, 'relative grid place-items-center rounded-full bg-accent text-white', celebrating && 'animate-check-fill')}>
          <CheckIcon animate={celebrating} />
        </button>
      </span>
    )
  }
  if (plan.state === 'not_completed' || plan.state === 'partial') {
    return (
      <button type="button" onClick={() => onOpen(plan)} aria-label={`Not completed: ${title}`}
        className={cx(size, 'grid shrink-0 place-items-center rounded-full bg-danger text-[10px] font-bold text-white')}>✕</button>
    )
  }
  const upcoming = plan.plan_date > today
  return (
    <button type="button" disabled={pending || upcoming} onClick={() => mark('completed')}
      aria-label={`Mark completed: ${title}`} title={upcoming ? 'You can tick this once the day starts' : 'Mark completed'}
      className={cx(size, 'grid shrink-0 place-items-center rounded-full border-2 text-transparent transition-colors',
        upcoming ? 'border-line' : 'border-accent/50 hover:border-accent hover:bg-accent hover:text-white')}>
      <CheckIcon animate={false} />
    </button>
  )
}

/** Title with a strike-through line that draws itself when the task is completed. */
function TaskTitle({ title, done, celebrating, className }: { title: string; done: boolean; celebrating: boolean; className?: string }) {
  return (
    <span className={cx(className, (done || celebrating) && 'text-muted transition-colors duration-500')}>
      <span className={cx(celebrating ? 'strike-draw' : done && 'line-through')}>{title}</span>
    </span>
  )
}

function TaskItem({ plan, onOpen, onChanged, showTime = false, hidePriority = false, card = false }: {
  plan: Plan; onOpen: (p: Plan, askReason?: boolean) => void; onChanged: () => void; showTime?: boolean
  hidePriority?: boolean // the list is already grouped by priority
  card?: boolean // white card inside a coloured priority column
}) {
  const { today } = useApp()
  const task = plan.task
  const done = plan.state === 'completed'
  const notDone = plan.state === 'not_completed' || plan.state === 'partial'
  const movable = isOpen(plan) && task.status === 'active'
  const meta = [
    notDone ? `Not completed${plan.reason_note ? `: ${plan.reason_note}` : plan.reason ? `: ${REASON_LABEL[plan.reason]}` : ''}` : null,
    task.estimated_minutes ? `~${formatMinutes(task.estimated_minutes)}` : null,
    task.deadline ? `Due ${formatShort(task.deadline)}` : null,
    plan.carried_from_date ? `From ${formatShort(plan.carried_from_date)}` : null,
  ].filter(Boolean)
  const quick = useQuickMark(plan, onChanged)
  const canMark = isOpen(plan) && plan.plan_date <= today && !quick.celebrating
  return (
    <li draggable={movable}
      onDragStart={(e) => setTaskDragData(e, task.id, rangeMinutes(plan.planned_time, plan.planned_end_time) ?? task.estimated_minutes)}
      className={cx('group rounded-lg px-2.5 py-2.5',
        card ? 'bg-card shadow-sm ring-1 ring-black/5 hover:ring-accent/40' : 'hover:bg-paper', movable && 'cursor-grab',
        quick.celebrating && 'animate-card-glow')}>
      <div className="flex items-start gap-3">
        <span className="pt-0.5"><CheckCircle plan={plan} quick={quick} onOpen={onOpen} /></span>
        <button type="button" onClick={() => onOpen(plan)} aria-label={`Open ${task.title}`} className="min-w-0 flex-1 text-left">
          <span className="flex items-start gap-1.5 text-sm font-medium">
            {task.priority === 'high' && !hidePriority && <span aria-label="High priority" className="mt-1.5 size-1.5 shrink-0 rounded-full bg-danger" />}
            <TaskTitle title={task.title} done={done} celebrating={quick.celebrating} className="line-clamp-2 break-words" />
          </span>
          {(showTime || meta.length > 0) && (
            <span className="block truncate text-xs">
              {showTime && (
                <span className={cx('tabular-nums', plan.planned_time ? 'font-medium text-accent' : 'text-muted')}>
                  {formatTimeRange(plan.planned_time, plan.planned_end_time)}
                </span>
              )}
              {showTime && meta.length > 0 && <span className="text-muted"> · </span>}
              {meta.length > 0 && <span className={notDone ? 'text-danger' : 'text-muted'}>{meta.join(' · ')}</span>}
            </span>
          )}
        </button>
        <button type="button" onClick={() => onOpen(plan)} aria-label={`More actions for ${task.title}`}
          className="shrink-0 rounded-md px-1.5 py-0.5 text-muted opacity-60 transition hover:bg-ink/5 hover:text-ink group-hover:opacity-100">⋯</button>
      </div>
      {canMark && (
        <div className="mt-2 flex gap-1.5 pl-8">
          <DoneButton plan={plan} quick={quick} />
          <button type="button" onClick={() => onOpen(plan, true)} aria-label={`Mark not completed: ${task.title}`} title="Mark not completed"
            className="flex-1 whitespace-nowrap rounded-md border border-danger/30 bg-card px-2 py-1 text-xs font-medium text-danger transition hover:bg-danger-soft">✕ Not done</button>
        </div>
      )}
    </li>
  )
}

/** Explicit "Done" button next to "Not done" (same action as the round check). */
function DoneButton({ plan, quick }: { plan: Plan; quick: QuickMark }) {
  const { mark, pending } = quick
  return (
    <button type="button" disabled={pending} onClick={() => mark('completed')} aria-label={`Done: ${plan.task.title}`} title="Mark completed"
      className="flex-1 whitespace-nowrap rounded-md border border-accent/30 bg-card px-2 py-1 text-xs font-medium text-accent transition hover:bg-accent-soft disabled:opacity-50">✓ Done</button>
  )
}

/** Calendar-style timeline: tasks are blocks sized by their length; click or drag empty space to add one. */
function Calendar({ date, timed, drop, onOpen, onChanged }: {
  date: string; timed: Plan[]; drop: ReturnType<typeof useDropToDay>
  onOpen: (p: Plan, askReason?: boolean) => void; onChanged: () => void
}) {
  const { today, settings } = useApp()
  const span = timelineSpan(settings)
  const [editHours, setEditHours] = useState(false)
  const pos = (t: string) => { // minutes into the user's day (00:30 after 23:00 when the day runs past midnight)
    const m = toMinutes(t)
    return span.pastMidnight && m < span.endRaw ? m + 1440 : m
  }

  // Lay out blocks: start, end, and side-by-side lanes for overlapping tasks.
  const blocks = timed.map((p) => {
    const start = pos(p.planned_time!)
    let end = p.planned_end_time ? pos(p.planned_end_time) : start + 30
    if (end <= start) end += 1440
    return { p, start, end: Math.max(end, start + 30), lane: 0, lanes: 1 }
  }).sort((a, b) => a.start - b.start || b.end - a.end)
  let cluster: typeof blocks = []
  let clusterEnd = -1
  const MAX_LANES = 4 // beyond this, extra overlapping tasks stack in the last column instead of becoming too thin
  const closeCluster = () => {
    const n = Math.min(MAX_LANES, Math.max(1, ...cluster.map((b) => b.lane + 1)))
    cluster.forEach((b) => { b.lanes = n; b.lane = Math.min(b.lane, n - 1) })
  }
  for (const b of blocks) {
    if (b.start >= clusterEnd) { closeCluster(); cluster = []; clusterEnd = -1 }
    const laneEnds: number[] = []
    cluster.forEach((c) => { laneEnds[c.lane] = Math.max(laneEnds[c.lane] ?? 0, c.end) })
    let lane = laneEnds.findIndex((e) => e <= b.start)
    if (lane === -1) lane = laneEnds.length
    b.lane = lane
    cluster.push(b)
    clusterEnd = Math.max(clusterEnd, b.end)
  }
  closeCluster()

  // Visible range: the user's hours, stretched to include any task outside them.
  let first = Math.floor(span.start / 60) * 60
  let last = Math.ceil(span.end / 30) * 30
  for (const b of blocks) {
    first = Math.min(first, Math.floor(b.start / 60) * 60)
    last = Math.max(last, Math.ceil(b.end / 30) * 30)
  }
  const slots = Array.from({ length: (last - first) / 30 }, (_, i) => first + i * 30)
  const height = (last - first) * PX
  const y = (m: number) => (m - first) * PX
  const nowPos = (() => {
    if (date !== today) return null
    const hm = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: settings.timezone }).format(new Date())
    const p = pos(hm)
    return p >= first && p <= last ? p : null
  })()

  // A drag is in progress somewhere on the page: let drops reach the time slots under the blocks.
  const [dragging, setDragging] = useState(false)
  useEffect(() => {
    const on = () => setDragging(true)
    const off = () => setDragging(false)
    document.addEventListener('dragstart', on)
    document.addEventListener('dragend', off)
    document.addEventListener('drop', off)
    return () => { document.removeEventListener('dragstart', on); document.removeEventListener('dragend', off); document.removeEventListener('drop', off) }
  }, [])

  // Click a free spot (or click and drag down) to create a task there.
  const [sel, setSel] = useState<{ anchor: number; current: number } | null>(null)
  const [creating, setCreating] = useState<{ start: string; end: string } | null>(null)
  const selecting = useRef(false)
  const selRef = useRef(sel)
  selRef.current = sel
  const rangeFor = (a: number, b: number, single: boolean) => {
    const from = slots[Math.min(a, b)]
    let to = single ? from + 60 : slots[Math.max(a, b)] + 30
    if (!span.pastMidnight) to = Math.min(to, 23 * 60 + 59)
    return { start: toHHMM(from % 1440), end: toHHMM(to % 1440), from, to }
  }
  useEffect(() => {
    const finish = () => {
      if (!selecting.current) return
      selecting.current = false
      const s = selRef.current
      if (s) setCreating(rangeFor(s.anchor, s.current, s.anchor === s.current))
    }
    window.addEventListener('mouseup', finish)
    return () => window.removeEventListener('mouseup', finish)
  })
  const preview = sel ? rangeFor(sel.anchor, sel.current, sel.anchor === sel.current) : null

  return (
    <section aria-label="Timeline" className={cx('min-w-0 rounded-xl border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]', sel && 'select-none')}>
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-4 py-3">
        <h3 className="font-semibold">Timeline</h3>
        <span className="text-xs text-muted">{timed.length}</span>
        <span className="ml-auto flex items-center gap-1 text-xs text-muted">
          {describeTimeline(settings)}
          <Button size="xs" variant="ghost" className="text-accent" onClick={() => setEditHours(true)} aria-label="Change timeline hours">Change</Button>
        </span>
      </header>

      <div className="relative flex px-2 pb-4 pt-3">
        {/* Hour labels */}
        <div className="relative w-16 shrink-0" style={{ height }} aria-hidden>
          {slots.filter((m) => m % 60 === 0).map((m) => (
            <span key={m} className="absolute right-3 -translate-y-1/2 text-[11px] text-muted" style={{ top: y(m) }}>
              {m === 1440 ? 'Midnight' : formatTime(toHHMM(m % 1440))}
            </span>
          ))}
          <span className="absolute right-3 -translate-y-1/2 text-[11px] font-medium text-muted" style={{ top: height }}>
            {formatTime(toHHMM(last % 1440))}
          </span>
        </div>

        {/* Grid */}
        <div className="relative flex-1 border-l border-line" style={{ height }}>
          {slots.map((m) => (
            <div key={`line-${m}`} aria-hidden className={cx('absolute inset-x-0 border-t',
              m === 1440 ? 'border-accent/40' : m % 60 === 0 ? 'border-line' : 'border-dashed border-line/60')} style={{ top: y(m) }} />
          ))}
          <div aria-hidden className="absolute inset-x-0 border-t border-line" style={{ top: height }} />

          {/* Half-hour targets: click / drag to create, drop to plan */}
          {slots.map((m, index) => {
            const start = toHHMM(m % 1440)
            return (
              <div key={m} {...drop.bind(date, { start })} aria-label={`Time slot ${formatTime(start)}`}
                onMouseEnter={() => { if (selecting.current) setSel((s) => (s ? { ...s, current: index } : s)) }}
                className={cx('absolute inset-x-0', drop.isOver(date, { start }) && 'z-30 bg-accent/10 outline-2 outline-dashed outline-accent')}
                style={{ top: y(m), height: 30 * PX }}>
                <button type="button" aria-label={`New task at ${formatTime(start)}`}
                  className="peer absolute inset-0 cursor-cell rounded-md focus-visible:bg-accent-soft"
                  onMouseDown={(e) => {
                    if (e.button !== 0) return
                    e.preventDefault()
                    selecting.current = true
                    setSel({ anchor: index, current: index })
                  }}
                  onClick={(e) => { if (e.detail === 0) setCreating(rangeFor(index, index, true)) /* keyboard */ }} />
                <span aria-hidden className="pointer-events-none absolute right-2 top-1 hidden text-[11px] text-accent/70 peer-hover:block">
                  + {formatTime(start)}
                </span>
              </div>
            )
          })}

          {/* Selection preview */}
          {preview && (
            <div aria-hidden className="pointer-events-none absolute inset-x-1 z-20 rounded-lg border border-accent/50 bg-accent/15 px-2 py-1 text-xs font-semibold text-accent"
              style={{ top: y(preview.from), height: (preview.to - preview.from) * PX }}>
              {formatTimeRange(preview.start, preview.end)}
            </div>
          )}

          {/* Now line */}
          {nowPos !== null && (
            <div aria-label="Now" className="pointer-events-none absolute inset-x-0 z-20 flex items-center" style={{ top: y(nowPos) }}>
              <span className="-ml-1 size-2 rounded-full bg-danger" />
              <span className="h-0.5 flex-1 bg-danger/70" />
            </div>
          )}

          {/* Task blocks */}
          <ul className={cx('absolute inset-0 z-10', dragging ? 'pointer-events-none' : 'pointer-events-none [&>li]:pointer-events-auto')}>
            {blocks.map((b) => (
              <Block key={b.p.id} plan={b.p} top={y(b.start)} height={(b.end - b.start) * PX}
                lane={b.lane} lanes={b.lanes} onOpen={onOpen} onChanged={onChanged} />
            ))}
          </ul>
        </div>
      </div>

      {creating && (
        <TaskFormDialog plannedDate={date} initialStart={creating.start} initialEnd={creating.end}
          onClose={() => { setCreating(null); setSel(null) }} onSaved={onChanged} />
      )}
      {editHours && <TimelineHoursDialog onClose={() => setEditHours(false)} />}
    </section>
  )
}

function Block({ plan, top, height, lane, lanes, onOpen, onChanged }: {
  plan: Plan; top: number; height: number; lane: number; lanes: number
  onOpen: (p: Plan, askReason?: boolean) => void; onChanged: () => void
}) {
  const { today } = useApp()
  const task = plan.task
  const done = plan.state === 'completed'
  const notDone = plan.state === 'not_completed' || plan.state === 'partial'
  const movable = isOpen(plan) && task.status === 'active'
  const compact = height < 44
  const quick = useQuickMark(plan, onChanged)
  const tone = done ? 'border-teal bg-teal-soft text-teal' : notDone ? 'border-danger bg-danger-soft text-danger' : 'border-accent bg-accent-soft text-accent'
  return (
    <li draggable={movable}
      onDragStart={(e) => setTaskDragData(e, task.id, rangeMinutes(plan.planned_time, plan.planned_end_time) ?? task.estimated_minutes)}
      className={cx('group absolute overflow-hidden rounded-lg border-l-[3px] px-2 py-1 shadow-sm transition-shadow hover:shadow-md', tone,
        movable && 'cursor-grab')}
      style={{ top: top + 1, height: height - 2, left: `calc(${(lane / lanes) * 100}% + 4px)`, width: `calc(${100 / lanes}% - 8px)` }}>
      <div className={cx('flex gap-1.5', compact ? 'items-center' : 'items-start')}>
        <CheckCircle plan={plan} quick={quick} onOpen={onOpen} small />
        <button type="button" onClick={() => onOpen(plan)} aria-label={`Open ${task.title}`} className="min-w-0 flex-1 text-left">
          <span className="block truncate text-xs font-semibold text-ink">
            <TaskTitle title={task.title} done={done} celebrating={quick.celebrating} />
            {compact && <span className="ml-1.5 font-normal text-muted">{formatTimeRange(plan.planned_time, plan.planned_end_time)}</span>}
          </span>
          {!compact && <span className="block truncate text-[11px] opacity-80">{formatTimeRange(plan.planned_time, plan.planned_end_time)}</span>}
          {!compact && notDone && <span className="block truncate text-[11px]">Not completed</span>}
        </button>
        {isOpen(plan) && plan.plan_date <= today && !quick.celebrating && (
          <button type="button" onClick={() => onOpen(plan, true)} aria-label={`Mark not completed: ${task.title}`} title="Mark not completed"
            className="shrink-0 rounded px-1 text-xs font-semibold text-danger/70 hover:bg-danger-soft hover:text-danger">✕</button>
        )}
      </div>
    </li>
  )
}
