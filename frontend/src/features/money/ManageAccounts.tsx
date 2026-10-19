import { useState } from 'react'
import { newId, patch, post } from '../../api'
import { Badge, Button, Dialog, ErrorNote, Segmented, cx, fieldBase, inputClass } from '../../components/ui'
import { useApp } from '../../context'
import { formatShort } from '../../dates'
import { notifyChanged, useAction } from '../../hooks'
import type { AccountType, MoneyAccount } from '../../types'
import { currencySymbol, formatMoney, parseAmount } from './money'

/** Add accounts, rename them, correct a starting balance, or archive one you no longer use. */
export function ManageAccounts({ accounts, onClose }: { accounts: MoneyAccount[]; onClose: () => void }) {
  const { settings } = useApp()
  const [type, setType] = useState<AccountType>('debit')
  const [name, setName] = useState('')
  const [balance, setBalance] = useState('')
  const [id, setId] = useState(newId)
  const action = useAction()
  const add = async () => {
    const cents = parseAmount(balance || '0')
    if (!name.trim() || cents === null) return
    if (await action.run(() => post('/finance/accounts', { id, name: name.trim(), type, balance_cents: cents }))) {
      setName(''); setBalance(''); setId(newId()); notifyChanged('money')
    }
  }
  return (
    <Dialog title="Manage accounts" onClose={onClose} wide footer={<Button onClick={onClose}>Done</Button>}>
      <div className="flex flex-col gap-5">
        <ul className="flex flex-col gap-2">
          {accounts.map((a) => <AccountRow key={a.id} account={a} currency={settings.currency} />)}
        </ul>
        <section className="flex flex-col gap-3 rounded-xl border border-line p-3">
          <h3 className="text-sm font-semibold">Add an account</h3>
          <Segmented label="Account type" value={type} onChange={setType} size="sm" options={[
            { value: 'debit', label: 'Debit account' }, { value: 'credit', label: 'Credit card' },
          ]} />
          <div className="grid gap-2 sm:grid-cols-[1fr_11rem_auto]">
            <label className="sr-only" htmlFor="new-acc-name">Name</label>
            <input id="new-acc-name" className={inputClass} placeholder="Name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
            <div className="flex items-center gap-1.5">
              <span className="text-sm text-muted">{currencySymbol(settings.currency)}</span>
              <label className="sr-only" htmlFor="new-acc-bal">{type === 'debit' ? 'Current balance' : 'Amount owed now'}</label>
              <input id="new-acc-bal" inputMode="decimal" className={inputClass} placeholder={type === 'debit' ? 'Balance' : 'Owed (0)'}
                value={balance} onChange={(e) => setBalance(e.target.value)} />
            </div>
            <Button variant="primary" pending={action.pending} disabled={!name.trim()} onClick={add}>Add</Button>
          </div>
          {action.error && <ErrorNote message={action.error} />}
        </section>
      </div>
    </Dialog>
  )
}

function AccountRow({ account, currency }: { account: MoneyAccount; currency: string }) {
  const [name, setName] = useState(account.name)
  const [opening, setOpening] = useState((account.opening_balance_cents / 100).toFixed(2))
  const action = useAction()
  const dirty = name.trim() !== account.name || parseAmount(opening) !== account.opening_balance_cents
  const save = async (body: object) => { if (await action.run(() => patch(`/finance/accounts/${account.id}`, body))) notifyChanged('money') }
  return (
    <li className={cx('flex flex-col gap-2 rounded-xl border border-line p-3', account.archived && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={account.type === 'debit' ? 'accent' : 'warn'}>{account.type === 'debit' ? 'Debit' : 'Credit card'}</Badge>
        <span className="text-sm text-muted">
          {account.type === 'debit' ? 'Available' : 'Owed'} now: <strong className="text-ink">{formatMoney(account.balance_cents, currency)}</strong>
        </span>
        {account.archived && <Badge>Archived</Badge>}
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_12rem_auto_auto]">
        <label className="sr-only" htmlFor={`name-${account.id}`}>Name</label>
        <input id={`name-${account.id}`} className={inputClass} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
        <div className="flex items-center gap-1.5" title={`Balance on ${formatShort(account.opened_on)}, when it was set up`}>
          <label className="whitespace-nowrap text-xs text-muted" htmlFor={`open-${account.id}`}>Start</label>
          <input id={`open-${account.id}`} inputMode="decimal" className={cx(fieldBase, 'w-full')} value={opening} onChange={(e) => setOpening(e.target.value)} />
        </div>
        <Button size="sm" variant="primary" disabled={!dirty || parseAmount(opening) === null} pending={action.pending}
          onClick={() => save({ name: name.trim(), opening_balance_cents: parseAmount(opening) })}>Save</Button>
        <Button size="sm" pending={action.pending} onClick={() => save({ archived: !account.archived })}>
          {account.archived ? 'Restore' : 'Archive'}
        </Button>
      </div>
      {action.error && <ErrorNote message={action.error} />}
    </li>
  )
}
