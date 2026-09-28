import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Field, Loading, ErrorBox, useLoad } from './ui'
import { inr } from '../lib/fmt'

/** Attach a bank transaction to what it was for.
 *  A credit takes a customer invoice; a debit takes a vendor invoice or an
 *  employee (salary or expense). The server caps the amount at what is left
 *  on the transaction and what is open on the invoice. */
export default function TxnAttach({ txn, onDone, onError, onClose }) {
  const { api } = useAuth()
  const opts = useLoad(() => api.attachables(txn.id), [txn.id, txn.attached])
  const credit = txn.credit > 0
  const [kind, setKind] = useState(credit ? 'CUST_INV' : 'VEND_INV')
  const [ref, setRef] = useState('')
  const [purpose, setPurpose] = useState('SALARY')
  const [amount, setAmount] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)

  const O = opts.data
  const list = !O ? [] : kind === 'CUST_INV' ? O.customer_invoices
    : kind === 'VEND_INV' ? O.vendor_invoices : O.employees
  const picked = list.find(x => String(x.id) === String(ref))

  // Preselect the first choice (an exact-amount invoice sorts first) and
  // suggest the amount: what is left on the transaction, capped by the invoice.
  useEffect(() => {
    if (!O) return
    const first = list[0]
    setRef(first ? String(first.id) : '')
  }, [O, kind]) // eslint-disable-line
  useEffect(() => {
    if (!O) return
    const cap = picked && picked.open != null ? Math.min(O.remaining, picked.open) : O.remaining
    setAmount(cap > 0 ? cap.toFixed(2) : '')
  }, [O, ref, kind]) // eslint-disable-line

  async function attach(e) {
    e.preventDefault()
    if (!ref) return
    setBusy(true)
    try {
      await api.addTxnLink(txn.id, { link_type: kind, ref_id: Number(ref),
        amount: amount ? Number(amount) : null,
        purpose: kind === 'EMPLOYEE' ? purpose : null, notes: notes || null })
      setNotes(''); onDone && onDone()
    } catch (x) { onError && onError(x.message) }
    finally { setBusy(false) }
  }

  if (opts.loading) return <Loading />
  if (opts.error) return <ErrorBox>{opts.error}</ErrorBox>

  const label = x => kind === 'EMPLOYEE'
    ? `${x.emp_code} — ${x.name}`
    : `${x.exact ? '✓ ' : ''}${x.doc_no} · ${x.party} · open ${inr(x.open)}`
  const empty = kind === 'CUST_INV' ? 'No customer tax invoice has an open amount left to attach.'
    : kind === 'VEND_INV' ? 'No vendor invoice has an open amount left to attach.'
    : 'No active employees. Add them on the Employees screen under Masters.'

  return (
    <form onSubmit={attach} className="attach">
      <div className="attach-hd">
        <span>{credit ? 'Money received' : 'Money paid out'} · {inr(O.amount)} ·{' '}
          <b>{inr(O.remaining)}</b> left to attach</span>
        <button type="button" className="rm" onClick={onClose} title="Close">×</button>
      </div>
      {O.remaining <= 0
        ? <div className="fine">The whole transaction is attached. Remove an attachment to change it.</div>
        : <div className="row">
          {!credit && <Field label="Attach to">
            <select value={kind} onChange={e => setKind(e.target.value)}>
              <option value="VEND_INV">Vendor invoice</option>
              <option value="EMPLOYEE">Employee — salary or expense</option>
            </select></Field>}
          <Field label={kind === 'CUST_INV' ? 'Customer invoice'
            : kind === 'VEND_INV' ? 'Vendor invoice' : 'Employee'}
            hint={kind !== 'EMPLOYEE' && list.some(x => x.exact) ? '✓ matches this amount exactly' : undefined}>
            {list.length
              ? <select value={ref} onChange={e => setRef(e.target.value)}>
                  {list.map(x => <option key={x.id} value={x.id}>{label(x)}</option>)}</select>
              : <div className="fine" style={{ paddingTop: 9 }}>{empty}</div>}
          </Field>
          {kind === 'EMPLOYEE' && <Field label="Paid as">
            <select value={purpose} onChange={e => setPurpose(e.target.value)}>
              <option value="SALARY">Salary</option>
              <option value="EXPENSE">Expense reimbursement</option>
            </select></Field>}
          <Field label="Amount" hint={picked && picked.open != null
            ? `Invoice total ${inr(picked.total)}` : undefined}>
            <input className="mono" type="number" step="0.01" min="0.01" value={amount}
              onChange={e => setAmount(e.target.value)} /></Field>
          <Field label="Note" hint="Optional">
            <input maxLength={200} value={notes} onChange={e => setNotes(e.target.value)} /></Field>
          <Field label=" "><button className="btn btn-a" disabled={busy || !ref || !amount}>
            {busy ? 'Attaching…' : 'Attach'}</button></Field>
        </div>}
    </form>)
}

const TYPE_LABEL = { CUST_INV: 'Invoice', VEND_INV: 'Vendor bill', EMPLOYEE: 'Employee' }
const PURPOSE_LABEL = { SALARY: 'salary', EXPENSE: 'expense' }

/** The attachments already on a transaction, each removable. */
export function LinkChips({ links, onRemove }) {
  if (!links?.length) return null
  return (<div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
    {links.map(l => <span key={l.id} className="chip" title={l.notes || ''}>
      <span className="chip-k">{TYPE_LABEL[l.link_type]}</span>
      {l.ref}{l.link_type === 'EMPLOYEE' ? ` ${l.party} · ${PURPOSE_LABEL[l.purpose]}` : ` ${l.party}`}
      <span className="mono">{inr(l.amount)}</span>
      {onRemove && <button type="button" className="rm" title="Remove this attachment"
        onClick={() => onRemove(l)}>×</button>}
    </span>)}
  </div>)
}
