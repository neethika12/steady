import { createContext, useCallback, useContext, useEffect, useId, useState, type ReactNode } from 'react'
import { ApiError, get, post } from '../../api'
import { Button, Dialog, ErrorNote, Loading, Notice, Segmented, inputClass } from '../../components/ui'
import { clearDraftsOf, setDraftOwner } from '../journal/draft'
import { PasswordField, RecoveryCodePanel } from './fields'

export interface Account { id: string; name: string | null; email: string; has_recovery_code: boolean }
interface SessionInfo { user: Account | null; signup_enabled: boolean; min_password_length: number }

const AccountContext = createContext<{ account: Account; signOut: () => Promise<void>; refresh: () => Promise<void> } | null>(null)
export const useAccount = () => useContext(AccountContext)!

/** Shows the log-in screen until someone is signed in; then the app, for that account only. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [waking, setWaking] = useState(false)

  // Free hosting plans put the server to sleep when nobody has used it for a while; the first
  // request then fails or takes up to about a minute. Keep retrying quietly for up to 2 minutes.
  const load = useCallback(async () => {
    setError(null)
    const started = Date.now()
    for (let attempt = 0; ; attempt++) {
      try {
        const s = await get<SessionInfo>('/auth/session')
        if (s.user) setDraftOwner(s.user.id)
        setWaking(false)
        setSession(s)
        return
      } catch (err) {
        const retryable = err instanceof ApiError && (err.status === 0 || err.status >= 500)
        if (!retryable || Date.now() - started > 120_000) {
          setWaking(false)
          setError(err instanceof Error ? err.message : 'Couldn’t reach the server.')
          return
        }
        setWaking(true)
        await new Promise((r) => setTimeout(r, Math.min(2000 + attempt * 1000, 6000)))
      }
    }
  }, [])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const onSignedOut = () => void load()
    window.addEventListener('steady:auth-required', onSignedOut)
    return () => window.removeEventListener('steady:auth-required', onSignedOut)
  }, [load])

  const signOut = useCallback(async () => {
    const id = session?.user?.id
    try { await post('/auth/logout') } catch { /* signed out locally either way */ }
    if (id) clearDraftsOf(id)
    try { sessionStorage.clear() } catch { /* ignore */ }
    await load()
  }, [session, load])

  if (error) return <main className="mx-auto max-w-xl p-6"><ErrorNote message={error} onRetry={load} /></main>
  if (!session) return (
    <main className="mx-auto max-w-xl p-6">
      <Loading label={waking ? 'Waking up the server… this can take up to a minute after a quiet spell.' : 'Starting Steady…'} />
    </main>
  )
  if (!session.user) return <AuthScreen info={session} onDone={load} />
  return (
    // key: a different account always starts from a fresh app (no data left over in memory)
    <AccountContext.Provider key={session.user.id} value={{ account: session.user, signOut, refresh: load }}>
      {children}
    </AccountContext.Provider>
  )
}

type Mode = 'login' | 'signup' | 'forgot'

function AuthScreen({ info, onDone }: { info: SessionInfo; onDone: () => void }) {
  const [mode, setModeState] = useState<Mode>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [code, setCode] = useState('')
  const [notice, setNotice] = useState<string | null>(null) // shown on Log in after creating an account or resetting
  const [newCode, setNewCode] = useState<{ code: string; intro: string; then: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const id = useId()
  const signup = mode === 'signup' && info.signup_enabled
  const choosing = signup || mode === 'forgot' // typing a new password (twice)
  const tooShort = choosing && password.length > 0 && password.length < info.min_password_length
  const mismatch = choosing && confirm.length > 0 && confirm !== password

  const setMode = (m: Mode) => { setModeState(m); setError(null); setNotice(null); setPassword(''); setConfirm('') }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (choosing && (tooShort || password !== confirm)) {
      setError(password !== confirm ? 'The two passwords don’t match.' : null)
      return
    }
    setPending(true)
    setError(null)
    try {
      if (signup) {
        // Creating an account doesn't sign in: show the recovery code, then go to Log in.
        const r = await post<{ recovery_code: string }>('/auth/signup', { name, email, password })
        const first = name.trim().split(/\s+/)[0]
        setNewCode({ code: r.recovery_code, intro: `Your account is ready${first ? `, ${first}` : ''}. Here’s your recovery code, in case you ever forget your password:`,
          then: 'Log in with your email and password.' })
      } else if (mode === 'forgot') {
        const r = await post<{ recovery_code: string }>('/auth/reset-password', { email, recovery_code: code, new_password: password })
        setCode('')
        setNewCode({ code: r.recovery_code, intro: 'Your password was changed and other devices were signed out. Your old recovery code is used up; here’s your new one:',
          then: 'Log in with your new password.' })
      } else {
        await post('/auth/login', { email, password })
        onDone()
      }
      setPassword(''); setConfirm('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-paper px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <span aria-hidden className="grid size-10 place-items-center rounded-xl bg-ink text-base font-bold text-white">S</span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Steady</h1>
            <p className="text-sm text-muted">Plan your days. Build habits. Reflect. Track money.</p>
          </div>
        </div>
        <div className="rounded-2xl border border-line bg-card p-5 shadow-sm">
          {newCode ? (
            <RecoveryCodePanel code={newCode.code} email={email} intro={newCode.intro} continueLabel="Continue to log in"
              onContinue={() => { const then = newCode.then; setNewCode(null); setModeState('login'); setNotice(then) }} />
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-4" aria-label={signup ? 'Create account' : mode === 'forgot' ? 'Reset password' : 'Log in'}>
              {mode === 'forgot' ? (
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold">Reset your password</h2>
                  <Button size="xs" variant="ghost" className="ml-auto" onClick={() => setMode('login')}>Back to log in</Button>
                </div>
              ) : info.signup_enabled && (
                <Segmented label="Log in or create an account" value={mode} onChange={setMode}
                  options={[{ value: 'login', label: 'Log in' }, { value: 'signup', label: 'Create account' }]} />
              )}
              {notice && mode === 'login' && <p role="status" className="rounded-lg bg-teal-soft px-3 py-2 text-sm text-teal">{notice}</p>}
              {mode === 'forgot' && <p className="text-sm text-muted">Use the recovery code you saved when you created your account (or your latest one).</p>}
              {signup && (
                <div>
                  <label htmlFor={`${id}-name`} className="mb-1.5 block text-sm font-medium">Name</label>
                  <input id={`${id}-name`} required autoComplete="name" maxLength={80} className={inputClass}
                    value={name} onChange={(e) => setName(e.target.value)} />
                </div>
              )}
              <div>
                <label htmlFor={`${id}-email`} className="mb-1.5 block text-sm font-medium">Email</label>
                <input id={`${id}-email`} type="email" required autoComplete="email" className={inputClass}
                  value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              {mode === 'forgot' && (
                <div>
                  <label htmlFor={`${id}-code`} className="mb-1.5 block text-sm font-medium">Recovery code</label>
                  <input id={`${id}-code`} required autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false}
                    placeholder="XXXXX-XXXXX-XXXXX-XXXXX" className={`${inputClass} font-mono uppercase`} value={code} onChange={(e) => setCode(e.target.value)} />
                </div>
              )}
              <PasswordField id={`${id}-password`} label={mode === 'forgot' ? 'New password' : 'Password'} value={password} onChange={setPassword}
                autoComplete={choosing ? 'new-password' : 'current-password'} autoFocus={!!notice && mode === 'login'} invalid={tooShort}
                hint={choosing ? `At least ${info.min_password_length} characters. A short sentence works well.` : undefined} />
              {choosing && (
                <PasswordField id={`${id}-confirm`} label={mode === 'forgot' ? 'Confirm new password' : 'Confirm password'} value={confirm} onChange={setConfirm}
                  autoComplete="new-password" error={mismatch ? 'The two passwords don’t match.' : null} />
              )}
              {mode === 'login' && (
                <button type="button" className="-mt-2 self-end text-sm font-medium text-accent hover:underline" onClick={() => setMode('forgot')}>
                  Forgot password?
                </button>
              )}
              {error && <p role="alert" className="text-sm text-danger">{error}</p>}
              <Button type="submit" variant="primary" pending={pending} disabled={choosing && (tooShort || mismatch)}>
                {signup ? 'Create account' : mode === 'forgot' ? 'Reset password' : 'Log in'}
              </Button>
              {signup && <p className="text-xs text-muted">Your tasks, habits, journal and money are private to your account.</p>}
            </form>
          )}
        </div>
      </div>
    </main>
  )
}

/** Accounts without a recovery code (made before codes existed) get a gentle reminder. */
export function RecoveryReminder() {
  const { account } = useAccount()
  const [open, setOpen] = useState(false)
  const [later, setLater] = useState(() => { try { return sessionStorage.getItem('steady.recoveryLater') === '1' } catch { return false } })
  if (account.has_recovery_code || later) return open ? <RecoveryCodeDialog onClose={() => setOpen(false)} /> : null
  return (
    <div className="mb-4">
      <Notice tone="warn">
        <span className="mr-2">Set up a recovery code, so you can reset your password if you ever forget it.</span>
        <Button size="xs" variant="primary" onClick={() => setOpen(true)}>Set up</Button>{' '}
        <Button size="xs" variant="ghost" onClick={() => { setLater(true); try { sessionStorage.setItem('steady.recoveryLater', '1') } catch { /* ignore */ } }}>Later</Button>
      </Notice>
      {open && <RecoveryCodeDialog onClose={() => setOpen(false)} />}
    </div>
  )
}

/** Header menu: who's signed in, change password, recovery code, log out, delete account. */
export function AccountMenu() {
  const { account, signOut } = useAccount()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState<'password' | 'recovery' | 'delete' | null>(null)
  return (
    <div className="relative">
      <Button variant="ghost" size="sm" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(!open)}
        title={account.name ? `${account.name} (${account.email})` : account.email}>
        <span aria-hidden className="grid size-6 place-items-center rounded-full bg-accent-soft text-xs font-semibold uppercase text-accent">
          {(account.name || account.email)[0]}
        </span>
        <span className="sr-only">Account</span>
      </Button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-64 rounded-xl border border-line bg-card p-1.5 shadow-lg">
          <p className="truncate px-2.5 py-2 text-xs text-muted">Signed in as {account.name && <strong className="block truncate text-ink">{account.name}</strong>}<span className={account.name ? 'block truncate' : 'font-semibold text-ink'}>{account.email}</span></p>
          {[
            ['Change password', () => setDialog('password')],
            [account.has_recovery_code ? 'New recovery code' : 'Set up recovery code', () => setDialog('recovery')],
            ['Log out', () => void signOut()],
            ['Delete account…', () => setDialog('delete')],
          ].map(([label, fn]) => (
            <button key={label as string} role="menuitem" type="button"
              className={`block w-full rounded-lg px-2.5 py-2 text-left text-sm hover:bg-ink/5 ${label === 'Delete account…' ? 'text-danger' : ''}`}
              onClick={() => { setOpen(false); (fn as () => void)() }}>{label as string}</button>
          ))}
        </div>
      )}
      {dialog === 'password' && <ChangePassword onClose={() => setDialog(null)} />}
      {dialog === 'recovery' && <RecoveryCodeDialog onClose={() => setDialog(null)} />}
      {dialog === 'delete' && <DeleteAccount onClose={() => setDialog(null)} />}
    </div>
  )
}

function RecoveryCodeDialog({ onClose }: { onClose: () => void }) {
  const { account, refresh } = useAccount()
  const [password, setPassword] = useState('')
  const [code, setCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const id = useId()
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setPending(true); setError(null)
    try { setCode((await post<{ recovery_code: string }>('/auth/recovery-code', { password })).recovery_code) } catch (err) {
      setError(err instanceof Error ? err.message : 'That didn’t work.')
    } finally { setPending(false) }
  }
  return (
    <Dialog title={account.has_recovery_code ? 'New recovery code' : 'Set up a recovery code'} onClose={onClose}>
      {code ? (
        <RecoveryCodePanel code={code} email={account.email} continueLabel="Done"
          intro={account.has_recovery_code ? 'Here’s your new recovery code. Your old one no longer works.' : 'Here’s your recovery code:'}
          onContinue={() => { onClose(); void refresh() }} />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3 text-sm">
          <p>A recovery code lets you reset your password from the log-in screen (<em>Forgot password?</em>) if you forget it.
            {account.has_recovery_code && ' Making a new one replaces your current code.'}</p>
          <PasswordField id={`${id}-pw`} label="Your password" value={password} onChange={setPassword} autoComplete="current-password" />
          {error && <p role="alert" className="text-danger">{error}</p>}
          <div><Button type="submit" variant="primary" pending={pending}>Show my recovery code</Button></div>
        </form>
      )}
    </Dialog>
  )
}

function ChangePassword({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [pending, setPending] = useState(false)
  const id = useId()
  const mismatch = confirm.length > 0 && confirm !== next
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (next !== confirm) { setError('The two new passwords don’t match.'); return }
    setPending(true); setError(null)
    try { await post('/auth/password', { current_password: current, new_password: next }); setDone(true) } catch (err) {
      setError(err instanceof Error ? err.message : 'That didn’t work.')
    } finally { setPending(false) }
  }
  return (
    <Dialog title="Change password" onClose={onClose}>
      {done ? (
        <div className="flex flex-col gap-3 text-sm">
          <p>Your password was changed. Any other browsers signed in to this account have been signed out.</p>
          <div><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <PasswordField id={`${id}-cur`} label="Current password" value={current} onChange={setCurrent} autoComplete="current-password" />
          <PasswordField id={`${id}-new`} label="New password" value={next} onChange={setNext} autoComplete="new-password" />
          <PasswordField id={`${id}-confirm`} label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password"
            error={mismatch ? 'The two new passwords don’t match.' : null} />
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <div><Button type="submit" variant="primary" pending={pending} disabled={mismatch}>Change password</Button></div>
        </form>
      )}
    </Dialog>
  )
}

function DeleteAccount({ onClose }: { onClose: () => void }) {
  const { account, signOut } = useAccount()
  const [typed, setTyped] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const id = useId()
  const ready = typed.trim().toLowerCase() === 'delete' && password.length > 0
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setPending(true); setError(null)
    try {
      await post('/auth/delete-account', { password })
      clearDraftsOf(account.id)
      await signOut()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That didn’t work.')
      setPending(false)
    }
  }
  return (
    <Dialog title="Delete your account?" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3 text-sm">
        <p>This permanently deletes <strong>{account.email}</strong> and everything in it: tasks, habits, journal entries and money records. It can’t be undone.</p>
        <p className="text-muted">Want a copy first? Use <em>Settings → Download export</em> before you continue.</p>
        <div>
          <label htmlFor={`${id}-typed`} className="mb-1.5 block font-medium">Type <strong>delete</strong> to confirm</label>
          <input id={`${id}-typed`} className={inputClass} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
        <PasswordField id={`${id}-pw`} label="Your password" value={password} onChange={setPassword} autoComplete="current-password" />
        {error && <p role="alert" className="text-danger">{error}</p>}
        <div className="flex gap-2">
          <Button onClick={onClose}>Keep my account</Button>
          <Button type="submit" variant="danger" disabled={!ready} pending={pending}>Delete everything</Button>
        </div>
      </form>
    </Dialog>
  )
}
