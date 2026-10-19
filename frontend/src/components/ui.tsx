// Shared, accessible building blocks.

import {
  createContext, useCallback, useContext, useEffect, useId, useRef, useState,
  type ButtonHTMLAttributes, type ReactNode,
} from 'react'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')
export { cx }

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({
  variant = 'secondary', size = 'md', pending = false, className, children, disabled, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'xs' | 'sm' | 'md'; pending?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: 'bg-accent text-white border border-accent shadow-sm hover:bg-accent/90',
    secondary: 'bg-card text-ink border border-line hover:bg-paper',
    ghost: 'text-ink hover:bg-ink/5 border border-transparent',
    danger: 'bg-card text-danger border border-danger/30 hover:bg-danger-soft',
  }
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'xs' ? 'min-h-7 px-1.5 text-xs' : size === 'sm' ? 'min-h-8 px-2.5 text-sm' : 'min-h-10 px-3.5 text-sm',
        styles[variant], className,
      )}
    >
      {pending && <Spinner small />}
      {children}
    </button>
  )
}

export function Spinner({ small = false, label }: { small?: boolean; label?: string }) {
  return (
    <span role={label ? 'status' : undefined} className="inline-flex items-center gap-2 text-muted">
      <span
        aria-hidden
        className={cx('inline-block animate-spin rounded-full border-2 border-current border-t-transparent',
          small ? 'size-3.5' : 'size-5')}
      />
      {label && <span className="text-sm">{label}</span>}
    </span>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="flex justify-center py-8"><Spinner label={label} /></div>
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm text-danger">
      <span className="flex-1">{message}</span>
      {onRetry && <Button size="sm" variant="danger" onClick={onRetry}>Try again</Button>}
    </div>
  )
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' }) {
  return (
    <div className={cx('rounded-lg px-3 py-2 text-sm',
      tone === 'warn' ? 'bg-warn-soft text-warn' : 'bg-accent-soft text-accent')}>
      {children}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-4 py-8 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  )
}

export function Card({ children, className, ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLElement>) {
  return <section {...rest} className={cx('rounded-xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]', className)}>{children}</section>
}

export function Badge({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'warn' | 'danger'; title?: string }) {
  const tones = {
    neutral: 'bg-ink/5 text-muted',
    accent: 'bg-accent-soft text-accent',
    warn: 'bg-warn-soft text-warn',
    danger: 'bg-danger-soft text-danger',
  }
  return <span title={title} className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', tones[tone])}>{children}</span>
}

/** Modal dialog built on the native <dialog> element: traps focus, closes on Escape. */
export function Dialog({ title, onClose, children, footer, wide = false }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const el = ref.current
    if (el && !el.open) el.showModal()
    const previous = document.activeElement as HTMLElement | null
    return () => previous?.focus?.()
  }, [])
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => { e.preventDefault(); onClose() }}
      onClick={(e) => { if (e.target === ref.current) onClose() }}
      className={cx('m-auto w-[calc(100%-1.5rem)] rounded-2xl border border-line bg-card p-0 text-ink shadow-xl backdrop:bg-ink/30',
        wide ? 'max-w-3xl' : 'max-w-lg')}
    >
      <div className="flex max-h-[85dvh] flex-col">
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close dialog">✕</Button>
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </dialog>
  )
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  )
}

export const fieldBase = 'rounded-lg border border-line bg-card px-3 py-2 text-sm placeholder:text-muted/70 focus:border-accent'
export const inputClass = `w-full ${fieldBase}`

/** Accessible single-choice button group (radio semantics, arrow keys move selection). */
export function Segmented<T extends string>({ label, value, options, onChange, size = 'md' }: {
  label: string; value: T | null; options: { value: T; label: string }[]; onChange: (v: T) => void; size?: 'sm' | 'md'
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const current = Math.max(0, options.findIndex((o) => o.value === value))
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-lg bg-ink/5 p-1">
      {options.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => { refs.current[i] = el }}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={i === current ? 0 : -1}
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            const delta = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
            if (!delta) return
            e.preventDefault()
            const next = (i + delta + options.length) % options.length
            onChange(options[next].value)
            refs.current[next]?.focus()
          }}
          className={cx('rounded-md font-medium transition-colors',
            size === 'sm' ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm',
            o.value === value ? 'bg-card text-ink shadow-sm' : 'text-muted hover:text-ink')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Disclosure({ title, children, defaultOpen = false, right }: {
  title: string; children: ReactNode; defaultOpen?: boolean; right?: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <Card className="p-0">
      <div className="flex items-center gap-2 px-4 py-3">
        <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
          className="flex flex-1 items-center gap-2 text-left font-semibold">
          <span aria-hidden className={cx('inline-block text-muted transition-transform', open && 'rotate-90')}>›</span>
          {title}
        </button>
        {right}
      </div>
      {open && <div id={id} className="border-t border-line px-4 py-4">{children}</div>}
    </Card>
  )
}

// ---- toasts (announced to screen readers) ----

type Toast = { id: number; text: string; tone: 'info' | 'error' }
const ToastContext = createContext<(text: string, tone?: 'info' | 'error') => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)
  const push = useCallback((text: string, tone: 'info' | 'error' = 'info') => {
    const id = next.current++
    setToasts((t) => [...t.slice(-2), { id, text, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'error' ? 8000 : 4000)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <div key={t.id} role={t.tone === 'error' ? 'alert' : 'status'}
            className={cx('pointer-events-auto rounded-lg px-4 py-2 text-sm shadow-lg',
              t.tone === 'error' ? 'bg-danger text-white' : 'bg-ink text-white')}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
