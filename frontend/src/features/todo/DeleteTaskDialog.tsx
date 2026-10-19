import { del } from '../../api'
import { Button, Dialog, ErrorNote, useToast } from '../../components/ui'
import { notifyChanged, useAction } from '../../hooks'
import type { Task } from '../../types'

/** Permanent delete, always behind an explicit confirmation. */
export function DeleteTaskDialog({ task, onClose, onDeleted }: { task: Task; onClose: () => void; onDeleted?: () => void }) {
  const action = useAction()
  const toast = useToast()
  const confirm = async () => {
    if (await action.run(() => del(`/tasks/${task.id}`).then(() => true))) {
      toast('Task deleted')
      notifyChanged('tasks')
      onDeleted?.()
      onClose()
    }
  }
  return (
    <Dialog title="Delete this task?" onClose={onClose} footer={<>
      <Button onClick={onClose} autoFocus>Keep it</Button>
      <Button variant="danger" className="border-danger bg-danger text-white hover:bg-danger/90" pending={action.pending} onClick={confirm}>
        Delete permanently
      </Button>
    </>}>
      <div className="flex flex-col gap-3 text-sm">
        <p className="rounded-lg bg-paper p-3 font-medium">{task.title}</p>
        <p>
          This removes the task and its record on <strong>every day</strong> it was planned, including completed or
          not-completed days, so past completion numbers will change. <strong>It can’t be undone.</strong>
        </p>
        <p className="text-muted">If you just won’t do it, use <strong>Cancel task</strong> instead: that keeps the record but doesn’t count it.</p>
        {action.error && <ErrorNote message={action.error} />}
      </div>
    </Dialog>
  )
}
