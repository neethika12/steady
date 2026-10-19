import { useState } from 'react'
import { put } from '../../api'
import { useToast } from '../../components/ui'
import { formatShort, formatTimeRange, timelineSpan, toHHMM, toMinutes } from '../../dates'
import { useApp } from '../../context'
import { notifyChanged } from '../../hooks'
export const TASK_DRAG_TYPE = 'application/x-steady-task'

/** Extra drag data: the task's length in minutes, so it keeps its length when dropped on a time. */
export const DURATION_DRAG_TYPE = 'application/x-steady-minutes'

const accepts = (e: React.DragEvent) => e.dataTransfer.types.includes(TASK_DRAG_TYPE)

/**
 * Where a dropped task goes:
 *   'keep'          → that day, keeping its current time (week view)
 *   'anytime'       → that day with no time
 *   { start: '09:30' } → that day at that time; the end follows the task's length
 */
export type DropTarget = 'keep' | 'anytime' | { start: string }


export function endFor(start: string, minutes: number, pastMidnight = false): string | null {
  const end = toMinutes(start) + minutes
  if (pastMidnight) return toHHMM(end % 1440) // the user's day continues after midnight
  return end <= 23 * 60 + 59 ? toHHMM(end) : null // otherwise ranges stay within the calendar day
}

/** Drag data for a task: id plus its length (range length, estimate, or nothing). */
export function setTaskDragData(e: React.DragEvent, taskId: string, minutes: number | null) {
  e.dataTransfer.setData(TASK_DRAG_TYPE, taskId)
  if (minutes) e.dataTransfer.setData(DURATION_DRAG_TYPE, String(minutes))
  e.dataTransfer.effectAllowed = 'move'
}

export function rangeMinutes(start: string | null, end: string | null): number | null {
  return start && end ? toMinutes(end) - toMinutes(start) : null
}

export function useDropToDay(onChanged?: () => void) {
  const [over, setOver] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()
  const { settings } = useApp()
  const keyOf = (day: string, target: DropTarget) => `${day}|${typeof target === 'string' ? target : target.start}`

  const bind = (day: string, target: DropTarget = 'keep') => {
    const key = keyOf(day, target)
    return {
      onDragOver: (e: React.DragEvent) => {
        if (!accepts(e)) return
        e.preventDefault()
        e.stopPropagation() // the innermost target (a time slot) wins
        e.dataTransfer.dropEffect = 'move'
        setOver(key)
      },
      onDragLeave: (e: React.DragEvent) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver((o) => (o === key ? null : o))
      },
      onDrop: async (e: React.DragEvent) => {
        if (!accepts(e)) return
        e.preventDefault()
        e.stopPropagation()
        setOver(null)
        setError(null)
        const taskId = e.dataTransfer.getData(TASK_DRAG_TYPE)
        let body: Record<string, unknown> = { planned_date: day }
        let msg = `Planned for ${formatShort(day)}`
        if (target === 'anytime') {
          body = { ...body, planned_time: null, planned_end_time: null }
          msg = `Anytime on ${formatShort(day)}`
        } else if (target !== 'keep') {
          const minutes = Number(e.dataTransfer.getData(DURATION_DRAG_TYPE)) || 60
          const end = endFor(target.start, minutes, timelineSpan(settings).pastMidnight)
          body = { ...body, planned_time: target.start, planned_end_time: end }
          msg = `Planned ${formatTimeRange(target.start, end)}`
        }
        try {
          await put(`/tasks/${taskId}/schedule`, body)
          toast(msg)
          notifyChanged('tasks')
          onChanged?.()
        } catch (err) {
          setError((err as Error).message)
        }
      },
    }
  }

  return { over, error, bind, isOver: (day: string, target: DropTarget = 'keep') => over === keyOf(day, target) }
}
