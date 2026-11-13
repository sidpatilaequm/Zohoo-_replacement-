import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Field, Loading, ErrorBox, useLoad } from './ui'
import { inr } from '../lib/fmt'

// A balance left on an invoice up to this share of its total is most likely
// tax the customer (or we) deducted at source, so it is offered as TDS by
// default. A larger balance is more likely a part payment; the box can still
// be ticked by hand.
const TDS_HINT_SHARE = 0.12

/** Attach a bank transaction to what it was for.
 *
 *  Credit (money received): a customer invoice it settles, an employee paying
 *  money back, or a loan received from a director.
 *  Debit (money paid out): a vendor invoice it pays, an employee's salary or
 *  expense, or a loan repaid to a director.
 *
 *  An invoice can be settled across several transactions. On the one that
 *  closes it, the shortfall between the invoice and the money collected is
 *  booked as TDS, which then shows in the TDS register. The server caps the
 *  amount at what is left on the transaction and, with TDS, at what is open
 *  on the invoice. */
export default function TxnAttach({ txn, onDone, onError, onClose }) {
  const { api } = useAuth()
  const opts = useLoad(() => api.attachables(txn.id), [txn.id, txn.attached])
  const credit = txn.credit > 0
  const [kind, setKind] = useState(credit ? 'CUST_INV' : 'VEND_INV')
  const [ref, setRef] = useState('')
  const [purpose, setPurpose] = useState('SALARY')
  const [head, setHead] = useState('')
  const [amount, setAmount] = useState('')
  const [asTds, setAsTds] = useState(false)
  const [tds, setTds] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [docFile, setDocFile] = useState(null)
  const [docBusy, setDocBusy] = useState(false)
  const [nd, setNd] = useState({ name: '', din: '', pan: '' })   // new director
  const [want, setWant] = useState(null)   // pick this one once the list reloads

  const O = opts.data
  const card = O?.account_kind === 'CARD'
  const isInv = kind === 'CUST_INV' || kind === 'VEND_INV'
  const list = !O ? [] : kind === 'CUST_INV' ? O.customer_invoices
    : kind === 'VEND_INV' ? O.vendor_invoices
    : kind === 'EMPLOYEE' ? O.employees : O.directors
  const picked = list.find(x => String(x.id) === String(ref))
  const addingDirector = kind === 'DIRECTOR_LOAN' && (ref === '__new' || !list.length)

  // What would still be open on the invoice after this amount.
  const amt = Number(amount) || 0
  const balance = isInv && picked ? Math.round((picked.open - amt) * 100) / 100 : 0

  // Preselect the first choice (an exact-amount invoice sorts first) and
  // suggest the amount: what is left on the transaction, capped by the invoice.
  useEffect(() => {
    if (O?.expense_heads?.length && !head) setHead(String(O.expense_heads[0].id))
  }, [O]) // eslint-disable-line
  useEffect(() => {
    if (!O) return
    const keep = want && list.find(x => String(x.id) === want)
    const first = keep || list[0]
    setRef(first ? String(first.id) : '')
    if (keep) setWant(null)
  }, [O, kind]) // eslint-disable-line
  useEffect(() => {
    if (!O) return
    const cap = picked && picked.open != null ? Math.min(O.remaining, picked.open) : O.remaining
    setAmount(cap > 0 ? cap.toFixed(2) : '')
  }, [O, ref, kind]) // eslint-disable-line
  // Offer the balance as TDS whenever the amount or the invoice changes.
  useEffect(() => {
    if (!isInv || !picked || balance <= 0.005) { setAsTds(false); setTds(''); return }
    setTds(balance.toFixed(2))
    setAsTds(balance <= picked.total * TDS_HINT_SHARE)
  }, [ref, kind, amount, O]) // eslint-disable-line

  async function saveDirector() {
    if (!nd.name.trim()) return onError && onError("Give the director's name.")
    setBusy(true)
    try {
      const d = await api.addDirector({ name: nd.name.trim(), din: nd.din || null, pan: nd.pan || null })
      setNd({ name: '', din: '', pan: '' })
      setWant(String(d.id))
      opts.reload()
    } catch (x) { onError && onError(x.message) }
    finally { setBusy(false) }
  }

  async function attach(e) {
    e.preventDefault()
    if (!ref || ref === '__new') return

    setBusy(true)

    try {
      await api.addTxnLink(txn.id, {
        link_type: kind,
        ref_id: Number(ref),
        amount: amount ? Number(amount) : null,
        tds: isInv && asTds && Number(tds) > 0 ? Number(tds) : null,
        purpose: kind === 'EMPLOYEE' ? (credit ? 'REFUND' : purpose) : null,
        expense_id: kind === 'EMPLOYEE' && !credit && purpose === 'EXPENSE'
          ? Number(head) || null
          : null,
        notes: notes || null
      })

      if (docFile) {
        setDocBusy(true)

        try {
          await api.addStmtDocument(txn.id, docFile)
        } catch (x) {
          onError && onError(
            `Attachment saved, but document upload failed: ${x.message}`
          )
        } finally {
          setDocBusy(false)
        }
      }

      setNotes('')
      setDocFile(null)

      onDone && onDone(kind)
    } catch (x) {
      onError && onError(x.message)
    } finally {
      setBusy(false)
    }
  }

  if (opts.loading && !O) return <Loading />
  if (opts.error) return <ErrorBox>{opts.error}</ErrorBox>

  const label = x => kind === 'EMPLOYEE' ? `${x.emp_code} — ${x.name}`
    : kind === 'DIRECTOR_LOAN'
      ? `${x.name}${x.din ? ` · DIN ${x.din}` : ''} · owed ${inr(x.balance)}`
      : `${x.exact ? '✓ ' : ''}${x.doc_no} · ${x.party} · open ${inr(x.open)}`
  const empty = kind === 'CUST_INV' ? 'No customer tax invoice has an open amount left to attach.'
    : kind === 'VEND_INV' ? 'No vendor invoice has an open amount left to attach.'
    : 'No active employees. Add them on the Employees screen under Masters.'
  const refLabel = { CUST_INV: 'Customer invoice', VEND_INV: 'Vendor invoice',
    EMPLOYEE: 'Employee', DIRECTOR_LOAN: 'Director' }[kind]
  const tdsOver = isInv && asTds && picked && amt + (Number(tds) || 0) > picked.open + 0.005

  return (
    <form onSubmit={attach} className="attach">
      <div className="attach-hd">
        <span>{credit ? 'Money received' : 'Money paid out'} · {inr(O.amount)} ·{' '}
          <b>{inr(O.remaining)}</b> left to attach</span>
        <button type="button" className="rm" onClick={onClose} title="Close">×</button>
      </div>
      {O.remaining <= 0
        ? <div className="fine">The whole transaction is attached. Remove an attachment to change it.</div>
        : <>
        <div className="row">
          {!card && <Field label="Attach to">
            <select value={kind} onChange={e => setKind(e.target.value)}>
              {credit
                ? <><option value="CUST_INV">Customer invoice</option>
                    <option value="EMPLOYEE">Employee (money paid back)</option>
                    <option value="DIRECTOR_LOAN">Loan from a director</option></>
                : <><option value="VEND_INV">Vendor invoice</option>
                    <option value="EMPLOYEE">Employee</option>
                    <option value="DIRECTOR_LOAN">Loan repaid to a director</option></>}
            </select></Field>}

          <Field label={refLabel}
            hint={isInv && list.some(x => x.exact) ? '✓ matches this amount exactly'
              : kind === 'DIRECTOR_LOAN' && picked ? `Received ${inr(picked.received)} · repaid ${inr(picked.repaid)}`
              : undefined}>
            {kind === 'DIRECTOR_LOAN'
              ? <select value={list.length ? ref : '__new'} onChange={e => setRef(e.target.value)}>
                  {list.map(x => <option key={x.id} value={x.id}>{label(x)}</option>)}
                  <option value="__new">+ Add a director…</option></select>
              : list.length
                ? <select value={ref} onChange={e => setRef(e.target.value)}>
                    {list.map(x => <option key={x.id} value={x.id}>{label(x)}</option>)}</select>
                : <div className="fine" style={{ paddingTop: 9 }}>{empty}</div>}
          </Field>

          {kind === 'EMPLOYEE' && !credit && <Field label="Paid as">
            <select value={purpose} onChange={e => setPurpose(e.target.value)}>
              <option value="SALARY">Salary</option>
              <option value="EXPENSE">Expense reimbursement</option>
            </select></Field>}
          {kind === 'EMPLOYEE' && credit && <Field label="Received as">
            <div className="fine" style={{ paddingTop: 9 }}>Refund — advance or excess paid back</div>
          </Field>}
          {kind === 'EMPLOYEE' && !credit && purpose === 'EXPENSE' && <Field label="Expense head">
            {O.expense_heads?.length
              ? <select value={head} onChange={e => setHead(e.target.value)}>
                  {O.expense_heads.map(h => <option key={h.id} value={h.id}>
                    {h.exp_code} — {h.name}</option>)}</select>
              : <div className="fine" style={{ paddingTop: 9 }}>No expense heads yet. Add them on
                  the Expenses screen under Masters.</div>}</Field>}
        </div>

        {addingDirector && <div className="row">
          <Field label="Director's name">
            <input value={nd.name} maxLength={120}
              onChange={e => setNd(s => ({ ...s, name: e.target.value }))} /></Field>
          <Field label="DIN" hint="Optional · 8 digits">
            <input className="mono" value={nd.din} maxLength={8}
              onChange={e => setNd(s => ({ ...s, din: e.target.value.replace(/\D/g, '') }))} /></Field>
          <Field label="PAN" hint="Optional">
            <input className="mono" value={nd.pan} maxLength={10}
              onChange={e => setNd(s => ({ ...s, pan: e.target.value.toUpperCase() }))} /></Field>
          <Field label=" "><button type="button" className="btn" disabled={busy || !nd.name.trim()}
            onClick={saveDirector}>Save director</button></Field>
        </div>}

        {!addingDirector && <div className="row">
          <Field label={isInv ? (credit ? 'Amount collected' : 'Amount paid') : 'Amount'}
            hint={isInv && picked
              ? `Invoice ${inr(picked.total)}${picked.attached ? ` · from bank ${inr(picked.attached)}` : ''}${picked.receipts > 0.005 ? ` · receipts ${inr(picked.receipts)}` : ''}${picked.tds ? ` · TDS ${inr(picked.tds)}` : ''}${kind === 'CUST_INV' ? ' · posts the receipt on Customer Payments' : ''}`
              : undefined}>
            <input className="mono" type="number" step="0.01" min="0.01" value={amount}
              onChange={e => setAmount(e.target.value)} /></Field>

          {isInv && picked && balance > 0.005 && <Field label="Balance on invoice"
            hint={asTds ? 'Booked as TDS — shows in the TDS register'
              : 'Left open for a later payment'}>
            <label className="check">
              <input type="checkbox" checked={asTds} onChange={e => setAsTds(e.target.checked)} />
              <span>{inr(balance)} is TDS {credit ? 'deducted by the customer' : 'we deducted'}</span>
            </label></Field>}

          {isInv && asTds && <Field label="TDS" hint={tdsOver ? 'More than the balance' : 'Edit if only part is TDS'}>
            <input className="mono" type="number" step="0.01" min="0" value={tds}
              onChange={e => setTds(e.target.value)} /></Field>}

          <Field label="Note" hint="Optional">
            <input
              maxLength={200}
              value={notes}
              onChange={e => setNotes(e.target.value)}
            />
          </Field>

          <Field
            label="Supporting document"
            hint="Optional · max 10 MB"
          >
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.heic,.doc,.docx,.xls,.xlsx,.csv,.txt,.eml,.msg,.zip"
              onChange={e => setDocFile(e.target.files[0] || null)}
            />
          </Field>

          <Field label=" ">
            <button
              className="btn btn-a"
              disabled={
                busy ||
                docBusy ||
                !ref ||
                !amount ||
                tdsOver ||
                (kind === 'EMPLOYEE' && !credit && purpose === 'EXPENSE' && !head)
              }
            >
              {busy || docBusy ? 'Saving…' : 'Attach'}
            </button>
          </Field>
        </div>}
      </>}
    </form>)
}

const TYPE_LABEL = { CUST_INV: 'Invoice', VEND_INV: 'Vendor bill', EMPLOYEE: 'Employee',
  DIRECTOR_LOAN: 'Director loan' }
const PURPOSE_LABEL = { SALARY: 'salary', EXPENSE: 'expense', REFUND: 'refund' }

/** The attachments already on a transaction, each removable. With onTds, an
 *  invoice whose remaining balance is small enough to be TDS (not a part
 *  payment still to come) can have that balance booked as TDS. A larger
 *  balance can still be booked as TDS from the attach form. */
export function LinkChips({ links, onRemove, onTds }) {
  if (!links?.length) return null
  return (<div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
    {links.map(l => <span key={l.id} className="chip" title={l.notes || ''}>
      <span className="chip-k">{TYPE_LABEL[l.link_type]}</span>
      {l.link_type === 'EMPLOYEE'
        ? `${l.ref} ${l.party} · ${l.expense ? l.expense : PURPOSE_LABEL[l.purpose]}`
        : l.link_type === 'DIRECTOR_LOAN' ? l.party
        : `${l.ref} ${l.party}`}
      <span className="mono">{inr(l.amount)}</span>
      {l.tds > 0 && <span className="mono" title="Tax deducted at source on this invoice">
        + TDS {inr(l.tds)}</span>}
      {onTds && (l.link_type === 'CUST_INV' || l.link_type === 'VEND_INV') &&
        l.invoice_open > 0.005 && l.invoice_open <= l.invoice_total * TDS_HINT_SHARE &&
        <button type="button" className="btn btn-sm" style={{ padding: '0 6px' }}
          title={`Book the ${inr(l.invoice_open)} still open on ${l.ref} as TDS`}
          onClick={() => onTds(l)}>{inr(l.invoice_open)} as TDS</button>}
      {onRemove && <button type="button" className="rm" title="Remove this attachment"
        onClick={() => onRemove(l)}>×</button>}
    </span>)}
  </div>)
}
