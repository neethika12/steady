import { useState } from 'react'
import { Button, cx, inputClass } from '../../components/ui'

/** A password box with an eye button to show or hide what was typed. */
export function PasswordField({ id, label, value, onChange, autoComplete, invalid, hint, error, autoFocus }: {
  id: string; label: string; value: string; onChange: (v: string) => void
  autoComplete: 'current-password' | 'new-password'; invalid?: boolean; hint?: string; error?: string | null; autoFocus?: boolean
}) {
  const [shown, setShown] = useState(false)
  const note = error || hint
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}</label>
      <div className="relative">
        <input id={id} type={shown ? 'text' : 'password'} required autoComplete={autoComplete} autoFocus={autoFocus}
          autoCapitalize="off" autoCorrect="off" spellCheck={false}
          className={cx(inputClass, 'pr-11')} value={value} onChange={(e) => onChange(e.target.value)}
          aria-invalid={invalid || !!error} aria-describedby={note ? `${id}-note` : undefined} />
        <button type="button" onClick={() => setShown(!shown)} aria-pressed={shown}
          aria-label={shown ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`} title={shown ? 'Hide' : 'Show'}
          className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-lg text-muted hover:text-ink focus-visible:text-ink">
          <EyeIcon off={shown} />
        </button>
      </div>
      {note && <p id={`${id}-note`} className={cx('mt-1 text-xs', error ? 'text-danger' : 'text-muted')}>{note}</p>}
    </div>
  )
}

function EyeIcon({ off }: { off: boolean }) {
  const common = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
    strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }
  return off ? (
    <svg {...common}><path d="M3 3l18 18" /><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" /><path d="M9.9 5.1A9.7 9.7 0 0 1 12 5c5 0 8.5 4.3 9.5 7a13 13 0 0 1-2.4 3.6M6.1 6.1C4.1 7.4 2.9 9.4 2.5 12c1 2.7 4.5 7 9.5 7a9.6 9.6 0 0 0 4.4-1" /></svg>
  ) : (
    <svg {...common}><path d="M2.5 12C3.5 9.3 7 5 12 5s8.5 4.3 9.5 7c-1 2.7-4.5 7-9.5 7s-8.5-4.3-9.5-7z" /><circle cx="12" cy="12" r="3" /></svg>
  )
}

/** Shows a new recovery code once, with Copy and Download, and asks the person to confirm they saved it. */
export function RecoveryCodePanel({ code, email, intro, onContinue, continueLabel }: {
  code: string; email: string; intro: string; onContinue: () => void; continueLabel: string
}) {
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true) } catch { setCopied(false) }
  }
  const download = () => {
    const text = `Steady recovery code\n\nAccount: ${email}\nRecovery code: ${code}\n\nUse it on the log-in screen: "Forgot password?".\nEach code works once; you'll get a new one when you use it.\n`
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'steady-recovery-code.txt'
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="flex flex-col gap-3" aria-label="Recovery code" role="group">
      <p className="text-sm">{intro}</p>
      <p className="rounded-xl border border-accent/30 bg-accent-soft px-3 py-3 text-center font-mono text-lg font-semibold tracking-wider text-accent select-all"
        data-testid="recovery-code">{code}</p>
      <div className="flex gap-2">
        <Button size="sm" onClick={copy}>{copied ? 'Copied ✓' : 'Copy'}</Button>
        <Button size="sm" onClick={download}>Download</Button>
      </div>
      <p className="text-xs text-muted">
        Keep it somewhere safe, like a password manager or a note only you can see. If you forget your password, this
        code is the only way back in. It works once; you get a new one each time you use it.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-accent" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
        I’ve saved my recovery code
      </label>
      <Button variant="primary" disabled={!saved} onClick={onContinue}>{continueLabel}</Button>
    </div>
  )
}
