import { Fragment, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Alert, Tag, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import TxnAttach, { LinkChips } from '../components/TxnAttach'
import { inr, money, gd } from '../lib/fmt'

const thisMonth = () => new Date().toISOString().slice(0, 7)

export default function BankStatements() {
  const { api } = useAuth()
  const accounts = useLoad(() => api.stmtAccounts())
  const [acct, setAcct] = useState('')
  const [period, setPeriod] = useState(thisMonth())
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flash, showFlash] = useFlash()
  const [na, setNa] = useState({ label: '', number_hint: '' })
  const [open, setOpen] = useState(null)      // transaction whose attach form is showing
  const [show, setShow] = useState('ALL')     // ALL | OPEN (not fully attached)

  const banks = (accounts.data || []).filter(a => a.kind === 'BANK')
  const aid = Number(acct) || banks[0]?.id
  const txns = useLoad(() => aid ? api.stmtTxns(aid, period) : [], [aid, period])
  const ledger = useLoad(() => api.expenseLedger(period), [period])

  async function addAccount(e) {
    e.preventDefault()
    try {
      await api.addStmtAccount({ kind: 'BANK', label: na.label, number_hint: na.number_hint || null })
      setNa({ label: '', number_hint: '' }); accounts.reload()
      showFlash('Bank account added.')
    } catch (x) { showFlash(x.message, 'bad') }
  }

  async function doUpload(e) {
    e.preventDefault()
    if (!file) return showFlash('Choose the statement file first.', 'bad')
    setBusy(true)
    try {
      const r = await api.uploadStmt(aid, period, file)
      showFlash(r.saved
        ? `${r.saved} transaction(s) saved${r.duplicates_skipped ? `, ${r.duplicates_skipped} already on record` : ''}.`
        : r.note || 'Nothing new in this file.')
      setFile(null); txns.reload(); ledger.reload()
    } catch (x) { showFlash(x.message, 'bad') }
    finally { setBusy(false) }
  }

  async function removeLink(l) {
    if (!window.confirm(`Remove ${l.ref} (${inr(l.amount)}) from this transaction?`)) return
    try { await api.delTxnLink(l.id); txns.reload(); ledger.reload() }
    catch (x) { showFlash(x.message, 'bad') }
  }

  if (accounts.loading) return <Loading />
  if (accounts.error) return <ErrorBox>{accounts.error}</ErrorBox>

  const all = txns.data || []
  const deb = all.reduce((s, t) => s + t.debit, 0)
  const cred = all.reduce((s, t) => s + t.credit, 0)
  const openCount = all.filter(t => t.unattached > 0.005).length
  const rows = show === 'OPEN' ? all.filter(t => t.unattached > 0.005) : all
  const L = ledger.data

  return (<>
    {flash}
    <Alert kind="ok"><b>Every transaction is saved, once.</b> Upload the account's monthly
      statement (the bank's PDF, or its CSV export) and each transaction in it is stored.
      Uploading the same statement again cannot double anything — rows already on record are
      recognised and skipped. Then attach each credit to the customer invoice it settles, and
      each debit to the vendor invoice it pays or the employee it was paid to.</Alert>

    {!banks.length && <Panel title="Add the company's bank account first">
      <form onSubmit={addAccount}><div className="row">
        <Field label="Account label" hint="How this account is known, e.g. HDFC Current A/c">
          <input value={na.label} onChange={e => setNa(s => ({ ...s, label: e.target.value }))} required /></Field>
        <Field label="Last digits" hint="Only the last few digits, never the full number">
          <input value={na.number_hint} onChange={e => setNa(s => ({ ...s, number_hint: e.target.value }))} /></Field>
        <Field label=" "><button className="btn btn-a">Add account</button></Field>
      </div></form>
    </Panel>}

    {banks.length > 0 && <>
      <Panel title="Upload a monthly statement" right={
        <form onSubmit={addAccount} style={{ display: 'flex', gap: 6 }}>
          <input placeholder="New account label" value={na.label} style={{ width: 160 }}
            onChange={e => setNa(s => ({ ...s, label: e.target.value }))} />
          <button className="btn btn-sm" disabled={!na.label}>Add account</button>
        </form>}>
        <form onSubmit={doUpload}><div className="row">
          <Field label="Bank account">
            <select value={aid} onChange={e => setAcct(e.target.value)}>
              {banks.map(a => <option key={a.id} value={a.id}>
                {a.label}{a.number_hint ? ` ··${a.number_hint}` : ''}</option>)}
            </select></Field>
          <Field label="Statement month">
            <input type="month" value={period} onChange={e => setPeriod(e.target.value)} required /></Field>
          <Field label="Statement file" hint="PDF or the bank's CSV export">
            <input type="file" accept=".pdf,.csv,.txt"
              onChange={e => setFile(e.target.files[0] || null)} /></Field>
          <Field label=" "><button className="btn btn-a" disabled={busy || !file}>
            {busy ? 'Reading…' : 'Upload and save'}</button></Field>
        </div></form>
      </Panel>

      <Panel title={`Saved transactions — ${period}`}
        right={<>
          <span className="fine">Debits {money(deb)} · Credits {money(cred)}</span>
          <select value={show} onChange={e => setShow(e.target.value)} style={{ fontSize: 12 }}>
            <option value="ALL">All transactions</option>
            <option value="OPEN">Not yet attached ({openCount})</option>
          </select></>}>
        {txns.loading ? <Loading /> : txns.error ? <ErrorBox>{txns.error}</ErrorBox> :
          <Table head={['Date', 'Description', { label: 'Debit', align: 'r' },
            { label: 'Credit', align: 'r' }, 'Attached to', '']}
            empty={show === 'OPEN' ? 'Every transaction this month is attached.'
              : 'No transactions saved for this month yet.'}>
            {rows.map(t => <Fragment key={t.id}>
              <tr className={open === t.id ? 'row-open' : ''}>
                <td>{gd(t.date)}</td><td>{t.descr}</td>
                <td className="r mono">{t.debit ? inr(t.debit) : ''}</td>
                <td className="r mono">{t.credit ? inr(t.credit) : ''}</td>
                <td><LinkChips links={t.links} onRemove={removeLink} />
                  {t.links.length > 0 && t.unattached > 0.005 &&
                    <Tag kind="warn">{inr(t.unattached)} not attached</Tag>}</td>
                <td className="r">{(t.unattached > 0.005 || open === t.id) &&
                  <button type="button" className="btn btn-sm"
                    onClick={() => setOpen(open === t.id ? null : t.id)}>
                    {open === t.id ? 'Close' : t.credit ? 'Attach invoice' : 'Attach'}</button>}</td>
              </tr>
              {open === t.id && <tr className="row-attach"><td colSpan={6}>
                <TxnAttach txn={t} onClose={() => setOpen(null)}
                  onError={m => showFlash(m, 'bad')}
                  onDone={() => { showFlash('Attached.'); setOpen(null); txns.reload(); ledger.reload() }} />
              </td></tr>}
            </Fragment>)}
          </Table>}
      </Panel>
    </>}

    <Panel title={`Monthly expense ledger — tally for ${period}`}>
      {ledger.loading ? <Loading /> : ledger.error ? <ErrorBox>{ledger.error}</ErrorBox> : L && <>
        <Table head={['Source', { label: 'Count', align: 'r' }, { label: 'Amount', align: 'r' }, '']}>
          <tr><td>Vendor invoices booked (purchases)</td>
            <td className="r">{L.vendor_invoices.count}</td>
            <td className="r mono">{inr(L.vendor_invoices.total)}</td><td /></tr>
          <tr><td>Vendor payments recorded</td>
            <td className="r">{L.vendor_payments.count}</td>
            <td className="r mono">{inr(L.vendor_payments.total)}</td><td /></tr>
          {L.bank.map(b => <tr key={b.account}>
            <td>Bank debits — {b.account}</td><td className="r">{b.txns}</td>
            <td className="r mono">{inr(b.debits)}</td><td /></tr>)}
          <tr><td>Card spend allocated to company (director cards)</td><td className="r" />
            <td className="r mono">{inr(L.card_company_expense)}</td>
            <td>{L.card_unallocated > 0 &&
              <Tag kind="warn">{money(L.card_unallocated)} still unallocated</Tag>}</td></tr>
          <tr><td>Salary paid to employees (attached bank debits)</td><td className="r" />
            <td className="r mono">{inr(L.employee_salary)}</td><td /></tr>
          <tr><td>Expenses reimbursed to employees (attached bank debits)</td><td className="r" />
            <td className="r mono">{inr(L.employee_expense)}</td><td /></tr>
          {(L.employee_expense_by_head || []).map(h => <tr key={h.exp_code}>
            <td style={{ paddingLeft: 26, color: 'var(--muted)' }}>{h.exp_code} {h.name}</td>
            <td className="r" /><td className="r mono" style={{ color: 'var(--muted)' }}>
              {inr(h.amount)}</td><td /></tr>)}
          <tr style={{ fontWeight: 600 }}>
            <td>Expense recognised this month (invoices + company card spend + employees)</td>
            <td className="r" /><td className="r mono">{inr(L.expense_recognised)}</td><td /></tr>
        </Table>
        <div style={{ marginTop: 10 }}>
          {Math.abs(L.payments_vs_bank_gap) > 0.5
            ? <Alert kind="warn">Vendor payments recorded in the books differ from the bank
                debits saved this month by <b>{money(Math.abs(L.payments_vs_bank_gap))}</b>
                {' '}({L.payments_vs_bank_gap > 0 ? 'payments not yet visible in the statement'
                  : 'bank debits with no payment entry'}). Check missing statement uploads or
                unrecorded payments before closing the month.</Alert>
            : <Alert kind="ok">Vendor payments recorded and bank debits saved agree for this month.</Alert>}
          {Math.abs(L.invoices_vs_payments_gap) > 0.5 &&
            <Alert kind="ok">Purchases booked exceed payments made by{' '}
              <b>{money(L.invoices_vs_payments_gap)}</b> — normally a timing difference
              (invoices due but not yet paid), visible in Payables under Reports.</Alert>}
        </div>
      </>}
    </Panel>
  </>)
}
