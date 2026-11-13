import { Fragment, useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Alert, Tag, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import TxnAttach, { LinkChips } from '../components/TxnAttach'
import { inr, money, gd } from '../lib/fmt'
import { useFy } from '../lib/fy'

const thisMonth = () => new Date().toISOString().slice(0, 7)

/** v5.0 — the months of a financial year, for the view picker. */
export function fyMonths(info) {
  if (!info) return []
  const out = []; let [y, m] = info.start.slice(0, 7).split('-').map(Number)
  const last = info.end.slice(0, 7)
  for (;;) { const k = `${y}-${String(m).padStart(2, '0')}`; out.push(k); if (k >= last) break; m === 12 ? (y++, m = 1) : m++ }
  return out
}
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const viewName = v => !v ? 'all years' : /^FY/i.test(v) ? `FY ${v.slice(2)}` : `${MON[+v.slice(5) - 1]} ${v.slice(0, 4)}`

/** v5.0 — show the whole financial year chosen at the top, or one of its months. */
export function ViewPicker({ value, onChange }) {
  const top = useFy()
  const info = top.years.find(y => y.label === top.fy)
  return (<select value={value} onChange={e => onChange(e.target.value)} style={{ fontSize: 12 }} aria-label="Show">
    {top.fy ? <option value={top.param}>Whole {top.name}</option> : <option value="">All years</option>}
    {fyMonths(info).map(m => <option key={m} value={m}>{viewName(m)}</option>)}
  </select>)
}

export default function BankStatements() {
  const { api } = useAuth()
  const accounts = useLoad(() => api.stmtAccounts())
  const [acct, setAcct] = useState('')
  const [period, setPeriod] = useState(thisMonth())     // the month a statement is uploaded under
  // v5.0: what is shown opens on the financial year chosen at the top
  const top = useFy()
  const [view, setView] = useState(top.param)
  useEffect(() => { setView(top.param) }, [top.param])
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flash, showFlash] = useFlash()
  const [na, setNa] = useState({ label: '', number_hint: '' })
  const [open, setOpen] = useState(null)      // transaction whose attach form is showing
  const [show, setShow] = useState('ALL')     // ALL | OPEN (not fully attached)
  const [uploads, setUploads] = useState([])
  const [uploadsLoading, setUploadsLoading] = useState(false)

  const banks = (accounts.data || []).filter(a => a.kind === 'BANK')
  const aid = Number(acct) || banks[0]?.id
  async function loadUploads() {
      if (!aid) {
    setUploads([])
    return
  }

  setUploadsLoading(true)
  try {
    setUploads(await api.stmtUploads(aid))
  } catch (x) {
    showFlash(x.message, 'bad')
  } finally {
    setUploadsLoading(false)
  }
}
useEffect(() => {
  loadUploads()
}, [aid])
  const txns = useLoad(() => aid ? api.stmtTxns(aid, view) : [], [aid, view])
  const ledger = useLoad(() => view ? api.expenseLedger(view) : null, [view])
  const loans = useLoad(() => api.directorLoans(view), [view])

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
      setFile(null)
      loadUploads()
      txns.reload()
      ledger.reload()
      loans.reload()
    } catch (x) { showFlash(x.message, 'bad') }
    finally { setBusy(false) }
  }
  async function removeUpload(u) {
  if (!window.confirm(
    `Delete "${u.filename}" from ${u.period}? This removes the transactions first saved by this upload.`
  )) return

  try {
    await api.delStmtUpload(u.id)
    showFlash('Statement upload deleted.')
    loadUploads()
    txns.reload()
    ledger.reload()
    loans.reload()
  } catch (x) {
    showFlash(x.message, 'bad')
  }
}
  async function removeAccount() {
    if (!aid) return

    let imp
    try {
      imp = await api.stmtAccountImpact(aid)
    } catch (x) {
      return showFlash(x.message, 'bad')
    }

    const account = banks.find(a => a.id === aid)
    if (!account) return

    const lines = [
      `Delete the bank account "${account.label}" completely?`,
      '',
      `• ${imp.statements} uploaded statement(s) and ${imp.transactions} transaction(s) will be deleted.`
    ]

    if (imp.allocated) {
      lines.push(`• ${imp.allocated} transaction(s) marked company or personal — those decisions go too.`)
    }
    if (imp.attachments) {
      lines.push(`• ${imp.attachments} attachment(s) to invoices, employees or loans will be removed.`)
    }
    if (imp.recorded_payments) {
      lines.push(`• ${imp.recorded_payments} receipt(s) or payment(s) recorded from those attachments will be removed, so those invoices show as unpaid again.`)
    }

    lines.push(
      '',
      'Invoices, vendors, employees and loans themselves are not touched.',
      'This cannot be undone.'
    )

    let confirm = null

    if (imp.allocated || imp.attachments) {
      confirm = window.prompt(
        lines.join('\n') +
        `\n\nType the bank account name to confirm: ${account.label}`
      )

      if (confirm === null) return

      if (confirm.trim() !== account.label) {
        return showFlash(`The name did not match "${account.label}" — nothing was deleted.`, 'bad')
      }
    } else {
      if (!window.confirm(lines.join('\n'))) return
    }

    setBusy(true)

    try {
      const r = await api.delStmtAccount(aid, confirm)

      showFlash(
        `Deleted ${r.label} — ${r.statements} statement(s), ${r.transactions} transaction(s)` +
        (r.attachments ? `, ${r.attachments} attachment(s)` : '') +
        (r.payments_removed ? `, ${r.payments_removed} recorded receipt(s)/payment(s)` : '') +
        '.'
      )

      setAcct('')
      setUploads([])
      accounts.reload()
      txns.reload()
      ledger.reload()
      loans.reload()
    } catch (x) {
      showFlash(x.message, 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function removeLink(l) {
    const what = l.link_type === 'DIRECTOR_LOAN' ? `the loan entry for ${l.party}` : l.ref
    const tds = l.tds > 0 ? ` and its TDS of ${inr(l.tds)}` : ''
    const rec = l.payment_id ? '\n\nThe receipt it recorded on Customer Payments is removed too, ' +
      'so the invoice shows as unpaid (or part paid) again.' : ''
    if (!window.confirm(`Remove ${what} (${inr(l.amount)})${tds} from this transaction?${rec}`)) return
    try { await api.delTxnLink(l.id); txns.reload(); ledger.reload(); loans.reload() }
    catch (x) { showFlash(x.message, 'bad') }
  }

  // Book what is still open on an invoice as TDS, after the fact.
  // v5.0 — change the TDS and GST withheld on an invoice attachment
  async function setWithheld(l, tds, gst_tds) {
    try {
      const r = await api.setLinkWithheld(l.id, { tds, gst_tds })
      showFlash(`${l.ref}: TDS ${inr(r.tds)}, GST withheld ${inr(r.gst_tds)}` +
        (r.invoice_open > 0.005 ? ` · ${inr(r.invoice_open)} still open.` : ' · the invoice is settled.'))
      txns.reload()
      return true
    } catch (x) { showFlash(x.message, 'bad'); return false }
  }

  async function bookTds(l) {
    if (!window.confirm(`Book the ${inr(l.invoice_open)} still open on ${l.ref} as TDS ` +
      `${l.link_type === 'CUST_INV' ? 'deducted by the customer' : 'we deducted'}? ` +
      'It will show in the TDS register.')) return
    try {
      await api.setLinkTds(l.id, null)
      showFlash(`${inr(l.invoice_open)} booked as TDS on ${l.ref}.`)
      txns.reload()
    } catch (x) { showFlash(x.message, 'bad') }
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
      recognised and skipped. Then attach each credit to the customer invoice it settles, an
      employee paying money back, or a loan from a director — and each debit to the vendor
      invoice it pays, the employee it was paid to, or a director whose loan it repays.
      An invoice can be settled across several transactions; on the last one, whatever the
      invoice is still short is booked as <b>TDS</b> and appears in the TDS register. Attaching a
      customer invoice also records the receipt on Customer Payments, so the invoice is marked
      paid — no separate entry is needed.</Alert>

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
    <Panel
      title={`Statement upload history — ${aid ? (banks.find(a => a.id === aid)?.label || '') : ''}`}
      right={aid && <button
        type="button"
        className="btn btn-sm"
        style={{ color: 'var(--red)' }}
        disabled={busy}
        onClick={removeAccount}
      >
        {busy ? 'Deleting…' : 'Delete account'}
      </button>}
    >
  {uploadsLoading ? <Loading /> : uploads.length === 0 ? (
    <div className="fine">No statement uploads recorded for this account.</div>
  ) : (
    <Table head={[
      'Month',
      'File',
      { label: 'Transactions', align: 'r' },
      'Uploaded',
      ''
    ]}>
      {uploads.map(u => (
        <tr key={u.id}>
          <td>{u.period}</td>
          <td>{u.filename}</td>
          <td className="r">
            {u.saved} saved / {u.found} found
          </td>
          <td>{u.uploaded_by || '—'}</td>
          <td className="r">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => removeUpload(u)}
            >
              Delete
            </button>
          </td>
        </tr>
      ))}
    </Table>
  )}
</Panel>
      <Panel title={`Saved transactions — ${viewName(view)}`}
        right={<>
          <ViewPicker value={view} onChange={setView} />
          <span className="fine">Debits {money(deb)} · Credits {money(cred)}</span>
          <select value={show} onChange={e => setShow(e.target.value)} style={{ fontSize: 12 }}>
            <option value="ALL">All transactions</option>
            <option value="OPEN">Not yet attached ({openCount})</option>
          </select></>}>
        {txns.loading ? <Loading /> : txns.error ? <ErrorBox>{txns.error}</ErrorBox> :
          <Table head={['Date', 'Description', { label: 'Debit', align: 'r' },
            { label: 'Credit', align: 'r' }, 'Attached to', '']}
            empty={show === 'OPEN' ? `Every transaction in ${viewName(view)} is attached.`
              : `No transactions saved for ${viewName(view)} yet.`}>
            {rows.map(t => <Fragment key={t.id}>
              <tr className={open === t.id ? 'row-open' : ''}>
                <td>{gd(t.date)}</td><td>{t.descr}</td>
                <td className="r mono">{t.debit ? inr(t.debit) : ''}</td>
                <td className="r mono">{t.credit ? inr(t.credit) : ''}</td>
                <td><LinkChips links={t.links} onRemove={removeLink} onTds={bookTds} onWithheld={setWithheld} />
                  {t.links.length > 0 && t.unattached > 0.005 &&
                    <Tag kind="warn">{inr(t.unattached)} not attached</Tag>}</td>
                <td className="r">{(t.unattached > 0.005 || open === t.id) &&
                  <button type="button" className="btn btn-sm"
                    onClick={() => setOpen(open === t.id ? null : t.id)}>
                    {open === t.id ? 'Close' : 'Attach'}</button>}</td>
              </tr>
              {open === t.id && <tr className="row-attach"><td colSpan={6}>
                <TxnAttach txn={t} onClose={() => setOpen(null)}
                  onError={m => showFlash(m, 'bad')}
                  onDone={k => { showFlash(k === 'CUST_INV'
                    ? 'Attached — the receipt is recorded on Customer Payments and the invoice is marked paid (or part paid).'
                    : 'Attached.'); setOpen(null); txns.reload(); ledger.reload(); loans.reload() }} />
              </td></tr>}
            </Fragment>)}
          </Table>}
      </Panel>
    </>}

    {banks.length > 0 && <DirectorLoans loans={loans} period={viewName(view)} />}

    <Panel title={view ? `Expense ledger — tally for ${viewName(view)}` : 'Expense ledger — choose a year at the top'}>
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
          {L.employee_refunds > 0 && <tr><td>Received back from employees (attached bank credits)</td>
            <td className="r" /><td className="r mono">{inr(L.employee_refunds)}</td>
            <td className="fine">not netted off above</td></tr>}
          <tr style={{ fontWeight: 600 }}>
            <td>Expense recognised this month (invoices + company card spend + employees)</td>
            <td className="r" /><td className="r mono">{inr(L.expense_recognised)}</td><td /></tr>
        </Table>
        {(L.director_loans_received > 0 || L.director_loans_repaid > 0) &&
          <div className="fine" style={{ marginTop: 8 }}>Director loans this month are not
            expenses: {inr(L.director_loans_received)} received, {inr(L.director_loans_repaid)} repaid.
            See the loan account above.</div>}
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

/** Each director's loan account for the month: brought forward, received,
 *  repaid and owed at month end, from bank transactions attached to them. */
function DirectorLoans({ loans, period }) {
  if (loans.loading && !loans.data) return null
  if (loans.error) return <ErrorBox>{loans.error}</ErrorBox>
  const D = loans.data
  if (!D || (!D.directors.length && !D.entries.length)) return null
  return (
    <Panel title={`Loans from directors — ${period}`}
      right={<span className="fine">Owed at the end {money(D.total_owed)}</span>} bodyless>
      <Table head={['Director', 'DIN', { label: 'Brought forward', align: 'r' },
        { label: 'Received', align: 'r' }, { label: 'Repaid', align: 'r' },
        { label: 'Owed at the end', align: 'r' }]}
        empty="No director loans yet.">
        {D.directors.map(d => <tr key={d.id}>
          <td>{d.name}{!d.active && <> <Tag>inactive</Tag></>}</td>
          <td className="mono">{d.din || '—'}</td>
          <td className="r mono">{inr(d.opening)}</td>
          <td className="r mono">{d.received ? inr(d.received) : ''}</td>
          <td className="r mono">{d.repaid ? inr(d.repaid) : ''}</td>
          <td className="r mono"><b>{inr(d.closing)}</b></td>
        </tr>)}
      </Table>
      {D.entries.length > 0 && <Table head={['Date', 'Director', 'Bank account', 'Description',
        '', { label: 'Amount', align: 'r' }]}>
        {D.entries.map((e, i) => <tr key={i}>
          <td>{gd(e.date)}</td><td>{e.director}</td><td>{e.account}</td>
          <td>{e.descr}{e.notes && <div className="fine">{e.notes}</div>}</td>
          <td>{e.kind === 'RECEIVED' ? <Tag kind="ok">received</Tag> : <Tag>repaid</Tag>}</td>
          <td className="r mono">{inr(e.amount)}</td>
        </tr>)}
      </Table>}
    </Panel>)
}
