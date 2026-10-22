import { createContext, useCallback, useContext, useEffect, useId, useState, type ReactNode } from 'react'
import { ApiError, get, post } from '../../api'
import { Button, Dialog, ErrorNote, Loading, Segmented, inputClass } from '../../components/ui'
import { clearDraftsOf, setDraftOwner } from '../journal/draft'

export interface Account { id: string; name: string | null; email: string }
interface SessionInfo { user: Account | null; signup_enabled: boolean; min_password_length: number }

const AccountContext = createContext<{ account: Account; signOut: () => Promise<void> } | null>(null)
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
    <AccountContext.Provider key={session.user.id} value={{ account: session.user, signOut }}>
      {children}
    </AccountContext.Provider>
  )
}

function AuthScreen({ info, onDone }: { info: SessionInfo; onDone: () => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [created, setCreated] = useState<string | null>(null) // set after creating an account: "now log in"
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const id = useId()
  const signup = mode === 'signup' && info.signup_enabled
  const tooShort = signup && password.length > 0 && password.length < info.min_password_length

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (tooShort) return
    setPending(true)
    setError(null)
    try {
      if (signup) {
        // Creating an account doesn't sign in: go to Log in, with the email filled in.
        await post('/auth/signup', { name, email, password })
        setPassword('')
        setCreated(name.trim().split(/\s+/)[0])
        setMode('login')
      } else {
        await post('/auth/login', { email, password })
        setPassword('')
        onDone()
      }
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
        <form onSubmit={submit} className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-5 shadow-sm" aria-label={signup ? 'Create account' : 'Log in'}>
          {info.signup_enabled && (
            <Segmented label="Log in or create an account" value={mode} onChange={(m) => { setMode(m); setError(null); setCreated(null) }}
              options={[{ value: 'login', label: 'Log in' }, { value: 'signup', label: 'Create account' }]} />
          )}
          {created !== null && !signup && (
            <p role="status" className="rounded-lg bg-teal-soft px-3 py-2 text-sm text-teal">
              Your account is ready{created ? `, ${created}` : ''}. Log in with your email and password.
            </p>
          )}
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
          <div>
            <label htmlFor={`${id}-password`} className="mb-1.5 block text-sm font-medium">Password</label>
            <input id={`${id}-password`} type="password" required autoFocus={created !== null && !signup} autoComplete={signup ? 'new-password' : 'current-password'}
              className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)}
              aria-invalid={tooShort} aria-describedby={signup ? `${id}-hint` : undefined} />
            {signup && <p id={`${id}-hint`} className={tooShort ? 'mt-1 text-xs text-danger' : 'mt-1 text-xs text-muted'}>
              At least {info.min_password_length} characters. A short sentence works well.</p>}
          </div>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" variant="primary" pending={pending}>{signup ? 'Create account' : 'Log in'}</Button>
          {signup && <p className="text-xs text-muted">Your tasks, habits, journal and money are private to your account. There’s no password reset by email yet, so keep your password safe.</p>}
        </form>
      </div>
    </main>
  )
}

/** Header menu: who's signed in, change password, log out, delete account. */
export function AccountMenu() {
  const { account, signOut } = useAccount()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState<'password' | 'delete' | null>(null)
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
      {dialog === 'delete' && <DeleteAccount onClose={() => setDialog(null)} />}
    </div>
  )
}

function ChangePassword({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [pending, setPending] = useState(false)
  const id = useId()
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
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
          <div>
            <label htmlFor={`${id}-cur`} className="mb-1.5 block text-sm font-medium">Current password</label>
            <input id={`${id}-cur`} type="password" autoComplete="current-password" required className={inputClass} value={current} onChange={(e) => setCurrent(e.target.value)} />
          </div>
          <div>
            <label htmlFor={`${id}-new`} className="mb-1.5 block text-sm font-medium">New password</label>
            <input id={`${id}-new`} type="password" autoComplete="new-password" required className={inputClass} value={next} onChange={(e) => setNext(e.target.value)} />
          </div>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <div><Button type="submit" variant="primary" pending={pending}>Change password</Button></div>
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
        <div>
          <label htmlFor={`${id}-pw`} className="mb-1.5 block font-medium">Your password</label>
          <input id={`${id}-pw`} type="password" autoComplete="current-password" className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-danger">{error}</p>}
        <div className="flex gap-2">
          <Button onClick={onClose}>Keep my account</Button>
          <Button type="submit" variant="danger" disabled={!ready} pending={pending}>Delete everything</Button>
        </div>
      </form>
    </Dialog>
  )
}
