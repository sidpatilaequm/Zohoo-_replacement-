import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Field, Loading, ErrorBox, useLoad } from './ui'
import { inr } from '../lib/fmt'

// A balance left on an invoice up to this share of its total is most likely
// tax the customer (or we) withheld, so it is offered as withheld by default.
// A larger balance is more likely a part payment; the box can still be ticked.
const TDS_HINT_SHARE = 0.12
// GST TDS (CGST Act s.51) is 2% of the taxable value; common TDS rates.
const GST_TDS_RATE = 0.02
const TDS_RATES = [0.01, 0.02, 0.1]

export const GOVT_KINDS = [
  ['GST', 'GST payment'], ['TDS', 'TDS payment'], ['PF', 'PF payment'],
  ['ESI', 'ESI payment'], ['OTHER', 'Others (statutory)'],
]

const r2 = n => Math.round(n * 100) / 100
// The month a statutory payment is for: dues are paid the month after, so the
// month before the bank line's date (a challan paid in August is for July).
const monthBefore = iso => { const d = new Date((iso || new Date().toISOString()).slice(0, 10) + 'T00:00:00Z')
  d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() - 1); return d.toISOString().slice(0, 7) }

/** How a shortfall most likely splits: TDS at a common rate plus GST TDS at
 *  2% of the taxable value, when the figures fit to the rupee. */
function guessSplit(balance, taxable) {
  if (!taxable || balance <= 0) return null
  const gst = r2(taxable * GST_TDS_RATE)
  for (const rate of TDS_RATES) {
    const tds = r2(taxable * rate)
    if (Math.abs(tds + gst - balance) <= 1) return { tds: r2(balance - gst), gst, why: `TDS ${rate * 100}% + GST TDS 2% of the taxable value` }
  }
  return null
}

/** Attach a bank transaction to what it was for.
 *
 *  Credit (money received): a customer invoice it settles, an employee paying
 *  money back, or a loan received from a director.
 *  Debit (money paid out): a vendor invoice it pays, an employee's salary or
 *  expense, a loan repaid to a director, or (v5.0) a payment to the
 *  government — GST, TDS, PF, ESI or another statutory due.
 *
 *  An invoice can be settled across several transactions. When the money does
 *  not tally with what is open, the shortfall can be marked as withheld — TDS,
 *  GST withheld (GST TDS), or both — or left open for a later payment. Every
 *  payment already on the invoice, with its TDS and GST withheld, is shown. */
export default function TxnAttach({ txn, onDone, onError, onClose }) {
  const { api } = useAuth()
  const opts = useLoad(() => api.attachables(txn.id), [txn.id, txn.attached])
  const credit = txn.credit > 0
  const [kind, setKind] = useState(credit ? 'CUST_INV' : 'VEND_INV')
  const [ref, setRef] = useState('')
  const [purpose, setPurpose] = useState('SALARY')
  const [head, setHead] = useState('')
  const [amount, setAmount] = useState('')
  const [withhold, setWithhold] = useState(false)
  const [tds, setTds] = useState('')
  const [gst, setGst] = useState('')
  const [hint, setHint] = useState('')
  const [govt, setGovt] = useState({ kind: 'GST', period: monthBefore(txn.date), challan: '', descr: '' })
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [docFile, setDocFile] = useState(null)
  const [docBusy, setDocBusy] = useState(false)
  const [nd, setNd] = useState({ name: '', din: '', pan: '' })   // new director
  const [want, setWant] = useState(null)   // pick this one once the list reloads

  const O = opts.data
  const card = O?.account_kind === 'CARD'
  const isInv = kind === 'CUST_INV' || kind === 'VEND_INV'
  const isGovt = kind === 'GOVT'
  const list = !O || isGovt ? [] : kind === 'CUST_INV' ? O.customer_invoices
    : kind === 'VEND_INV' ? O.vendor_invoices
    : kind === 'EMPLOYEE' ? O.employees : O.directors
  const picked = list.find(x => String(x.id) === String(ref))
  const addingDirector = kind === 'DIRECTOR_LOAN' && (ref === '__new' || !list.length)

  // Every payment already on the picked invoice, with TDS and GST withheld.
  const history = useLoad(() => (isInv && picked ? api.invoicePayments(kind, picked.id) : null),
    [kind, picked?.id, O])

  // What would still be open on the invoice after this amount, before withholding.
  const amt = Number(amount) || 0
  const balance = isInv && picked ? r2(picked.open - amt) : 0
  const w = withhold ? (Number(tds) || 0) + (Number(gst) || 0) : 0
  const after = r2(balance - w)

  useEffect(() => {
    if (O?.expense_heads?.length && !head) setHead(String(O.expense_heads[0].id))
  }, [O]) // eslint-disable-line
  useEffect(() => {
    if (!O || isGovt) return
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
  // Offer the balance as withheld whenever the amount or the invoice changes,
  // split into TDS and GST TDS when the figures fit a common pattern.
  useEffect(() => {
    if (!isInv || !picked || balance <= 0.005) { setWithhold(false); setTds(''); setGst(''); setHint(''); return }
    const g = guessSplit(balance, picked.taxable)
    if (g) { setTds(g.tds.toFixed(2)); setGst(g.gst.toFixed(2)); setHint(`Looks like ${g.why}`) }
    else { setTds(balance.toFixed(2)); setGst(''); setHint('') }
    setWithhold(balance <= picked.total * TDS_HINT_SHARE)
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
    if (!isGovt && (!ref || ref === '__new')) return
    setBusy(true)
    try {
      await api.addTxnLink(txn.id, {
        link_type: kind,
        ref_id: isGovt ? null : Number(ref),
        amount: amount ? Number(amount) : null,
        tds: isInv && withhold && Number(tds) > 0 ? Number(tds) : null,
        gst_tds: isInv && withhold && Number(gst) > 0 ? Number(gst) : null,
        purpose: kind === 'EMPLOYEE' ? (credit ? 'REFUND' : purpose) : null,
        expense_id: kind === 'EMPLOYEE' && !credit && purpose === 'EXPENSE' ? Number(head) || null : null,
        govt_kind: isGovt ? govt.kind : null,
        govt_period: isGovt && govt.period ? govt.period : null,
        challan_ref: isGovt ? govt.challan || null : null,
        govt_descr: isGovt ? govt.descr || null : null,
        notes: notes || null,
      })
      if (docFile) {
        setDocBusy(true)
        try { await api.addStmtDocument(txn.id, docFile) }
        catch (x) { onError && onError(`Attachment saved, but document upload failed: ${x.message}`) }
        finally { setDocBusy(false) }
      }
      setNotes(''); setDocFile(null)
      onDone && onDone(kind)
    } catch (x) { onError && onError(x.message) }
    finally { setBusy(false) }
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
  const over = isInv && withhold && after < -0.005
  const who = credit ? 'the customer' : 'us'
  const fill = (setter, v) => setter(r2(v).toFixed(2))
  const H = history.data

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
                    <option value="DIRECTOR_LOAN">Loan repaid to a director</option>
                    <option value="GOVT">Government filings (statutory payment)</option></>}
            </select></Field>}

          {isGovt ? <>
            <Field label="Paid towards">
              <select value={govt.kind} onChange={e => setGovt({ ...govt, kind: e.target.value })}>
                {GOVT_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select></Field>
            <Field label="For the month" hint="The month the dues are for">
              <input type="month" value={govt.period} onChange={e => setGovt({ ...govt, period: e.target.value })} /></Field>
            <Field label={govt.kind === 'GST' ? 'CPIN / CIN' : govt.kind === 'TDS' ? 'Challan no. / CIN' : govt.kind === 'PF' ? 'TRRN / ECR ref.' : 'Challan reference'}
              hint="Optional">
              <input className="mono" maxLength={40} value={govt.challan}
                onChange={e => setGovt({ ...govt, challan: e.target.value })} /></Field>
            {govt.kind === 'OTHER' && <Field label="What for" hint="e.g. professional tax, labour welfare fund">
              <input maxLength={120} value={govt.descr} onChange={e => setGovt({ ...govt, descr: e.target.value })} /></Field>}
          </> : <Field label={refLabel}
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
          </Field>}

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
                  {O.expense_heads.map(h => <option key={h.id} value={h.id}>{h.exp_code} — {h.name}</option>)}</select>
              : <div className="fine" style={{ paddingTop: 9 }}>No expense heads yet. Add them on
                  the Expenses screen under Masters.</div>}</Field>}
        </div>

        {/* v5.0 — the invoice so far: every payment, with TDS and GST withheld */}
        {isInv && picked && <>
          <div className="inv-sum">
            <span><span className="k">Invoice</span><b>{inr(picked.total)}</b></span>
            <span><span className="k">Taxable</span><b>{inr(picked.taxable)}</b></span>
            <span><span className="k">{credit ? 'Received so far' : 'Paid so far'}</span>
              <b>{inr(r2((picked.attached || 0) + (picked.receipts || 0)))}</b></span>
            <span><span className="k">TDS so far</span><b>{inr(picked.tds_total || 0)}</b></span>
            <span><span className="k">GST withheld so far</span><b>{inr(picked.gst_tds_total || 0)}</b></span>
            <span><span className="k">Open</span><b>{inr(picked.open)}</b></span>
          </div>
          {H && H.payments.length > 0 && <table className="paylist"><thead><tr>
            <th>Date</th><th>From</th><th className="r">Amount</th><th className="r">TDS</th><th className="r">GST withheld</th></tr></thead>
            <tbody>{H.payments.map((p, i) => <tr key={i}>
              <td className="mono">{p.date}</td><td className="fine">{p.source}</td>
              <td className="r">{inr(p.amount)}</td><td className="r">{p.tds ? inr(p.tds) : '—'}</td>
              <td className="r">{p.gst_tds ? inr(p.gst_tds) : '—'}</td></tr>)}</tbody></table>}
        </>}

        {addingDirector && <div className="row">
          <Field label="Director's name">
            <input value={nd.name} maxLength={120} onChange={e => setNd(s => ({ ...s, name: e.target.value }))} /></Field>
          <Field label="DIN" hint="Optional · 8 digits">
            <input className="mono" value={nd.din} maxLength={8}
              onChange={e => setNd(s => ({ ...s, din: e.target.value.replace(/\D/g, '') }))} /></Field>
          <Field label="PAN" hint="Optional">
            <input className="mono" value={nd.pan} maxLength={10}
              onChange={e => setNd(s => ({ ...s, pan: e.target.value.toUpperCase() }))} /></Field>
          <Field label=" "><button type="button" className="btn" disabled={busy || !nd.name.trim()}
            onClick={saveDirector}>Save director</button></Field>
        </div>}

        {!addingDirector && <>
        <div className="row">
          <Field label={isInv ? (credit ? 'Amount collected' : 'Amount paid') : 'Amount'}
            hint={kind === 'CUST_INV' ? 'Posts the receipt on Customer Payments'
              : kind === 'VEND_INV' ? 'Posts the payment on Vendor Payments' : undefined}>
            <input className="mono" type="number" step="0.01" min="0.01" value={amount}
              onChange={e => setAmount(e.target.value)} /></Field>
          <Field label="Note" hint="Optional">
            <input maxLength={200} value={notes} onChange={e => setNotes(e.target.value)} /></Field>
          <Field label="Supporting document" hint={isGovt ? 'The challan · max 10 MB' : 'Optional · max 10 MB'}>
            <input type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.heic,.doc,.docx,.xls,.xlsx,.csv,.txt,.eml,.msg,.zip"
              onChange={e => setDocFile(e.target.files[0] || null)} /></Field>
        </div>

        {/* v5.0 — the payment does not tally: say why */}
        {isInv && picked && balance > 0.005 && <div className={`short${over ? ' bad' : withhold && Math.abs(after) <= 0.005 ? ' ok' : ''}`}>
          <div><b>Does not tally: {inr(balance)} short</b> of the {inr(picked.open)} open on {picked.doc_no}.</div>
          <div className="row" style={{ marginTop: 6 }}>
            <Field label="The shortfall is">
              <select value={withhold ? 'W' : 'O'} onChange={e => setWithhold(e.target.value === 'W')}>
                <option value="W">Withheld by {who} — TDS / GST</option>
                <option value="O">Still to come — leave it open</option>
              </select></Field>
            {withhold && <>
              <Field label="TDS withheld" hint="Shows in the TDS register">
                <input className="mono" type="number" step="0.01" min="0" value={tds} onChange={e => setTds(e.target.value)} />
                <span className="qf">{TDS_RATES.map(rt => <button type="button" key={rt}
                  onClick={() => fill(setTds, picked.taxable * rt)}>{rt * 100}%</button>)}
                  <button type="button" onClick={() => fill(setTds, balance - (Number(gst) || 0))}>rest</button></span></Field>
              <Field label="GST withheld (GST TDS)" hint="2% of taxable · in the GST withheld register">
                <input className="mono" type="number" step="0.01" min="0" value={gst} onChange={e => setGst(e.target.value)} />
                <span className="qf"><button type="button" onClick={() => fill(setGst, picked.taxable * GST_TDS_RATE)}>2%</button>
                  <button type="button" onClick={() => setGst('')}>none</button>
                  <button type="button" onClick={() => fill(setGst, balance - (Number(tds) || 0))}>rest</button></span></Field>
              <Field label="Still open after this">
                <div className="mono" style={{ paddingTop: 9 }}><b>{inr(Math.max(after, 0))}</b>
                  {over && ' — more than the shortfall'}</div></Field>
            </>}
          </div>
          {withhold && hint && <div className="fine">{hint}. Check against the customer's certificate (Form 16A / GSTR-7).</div>}
        </div>}

        <div className="row">
          <Field label=" ">
            <button className="btn btn-a"
              disabled={busy || docBusy || (!isGovt && !ref) || !amount || over
                || (isGovt && govt.kind === 'OTHER' && !govt.descr.trim())
                || (kind === 'EMPLOYEE' && !credit && purpose === 'EXPENSE' && !head)}>
              {busy || docBusy ? 'Saving…' : 'Attach'}
            </button>
          </Field>
        </div>
        </>}
      </>}
    </form>)
}

const TYPE_LABEL = { CUST_INV: 'Invoice', VEND_INV: 'Vendor bill', EMPLOYEE: 'Employee',
  DIRECTOR_LOAN: 'Director loan', GOVT: 'Government' }
const PURPOSE_LABEL = { SALARY: 'salary', EXPENSE: 'expense', REFUND: 'refund' }

/** The attachments already on a transaction, each removable. With onTds, an
 *  invoice whose remaining balance is small enough to be withheld (not a part
 *  payment still to come) can have that balance booked as TDS. With
 *  onWithheld, the TDS and GST withheld on an invoice attachment can be
 *  changed (v5.0). */
export function LinkChips({ links, onRemove, onTds, onWithheld }) {
  const [edit, setEdit] = useState(null)        // { id, tds, gst }
  if (!links?.length) return null
  return (<div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
    {links.map(l => {
      const inv = l.link_type === 'CUST_INV' || l.link_type === 'VEND_INV'
      return <span key={l.id} className={`chip${l.link_type === 'GOVT' ? ' govt' : ''}`} title={l.notes || ''}>
        <span className="chip-k">{TYPE_LABEL[l.link_type]}</span>
        {l.link_type === 'EMPLOYEE'
          ? `${l.ref} ${l.party} · ${l.expense ? l.expense : PURPOSE_LABEL[l.purpose]}`
          : l.link_type === 'DIRECTOR_LOAN' ? l.party
          : l.link_type === 'GOVT' ? `${l.ref}${l.party ? ` · ${l.party}` : ''}`
          : `${l.ref} ${l.party}`}
        <span className="mono">{inr(l.amount)}</span>
        {l.tds > 0 && <span className="mono" title="Tax deducted at source on this invoice">+ TDS {inr(l.tds)}</span>}
        {l.gst_tds > 0 && <span className="mono gst" title="GST withheld (GST TDS) on this invoice">+ GST withheld {inr(l.gst_tds)}</span>}
        {inv && l.invoice_open > 0.005 && <span className="fine" title="Still open on the invoice">· {inr(l.invoice_open)} open</span>}
        {onTds && inv && l.invoice_open > 0.005 && l.invoice_open <= l.invoice_total * TDS_HINT_SHARE &&
          <button type="button" className="btn btn-sm" style={{ padding: '0 6px' }}
            title={`Book the ${inr(l.invoice_open)} still open on ${l.ref} as TDS`}
            onClick={() => onTds(l)}>{inr(l.invoice_open)} as TDS</button>}
        {onWithheld && inv && edit?.id !== l.id &&
          <button type="button" className="btn btn-sm" style={{ padding: '0 6px' }}
            title="Set the TDS and GST withheld on this invoice"
            onClick={() => setEdit({ id: l.id, tds: String(l.tds || ''), gst: String(l.gst_tds || '') })}>TDS / GST</button>}
        {edit?.id === l.id && <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
          <input className="mono" style={{ width: 80 }} placeholder="TDS" value={edit.tds}
            onChange={e => setEdit({ ...edit, tds: e.target.value })} />
          <input className="mono" style={{ width: 80 }} placeholder="GST" value={edit.gst}
            onChange={e => setEdit({ ...edit, gst: e.target.value })} />
          <button type="button" className="btn btn-sm btn-a" style={{ padding: '0 6px' }}
            onClick={async () => { const ok = await onWithheld(l, Number(edit.tds) || 0, Number(edit.gst) || 0); if (ok) setEdit(null) }}>Save</button>
          <button type="button" className="rm" onClick={() => setEdit(null)}>×</button></span>}
        {onRemove && <button type="button" className="rm" title="Remove this attachment"
          onClick={() => onRemove(l)}>×</button>}
      </span>
    })}
  </div>)
}
