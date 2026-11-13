import { useEffect, useMemo, useState } from 'react'
import { useFyRange } from '../lib/fy'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { inr, gd } from '../lib/fmt'
import { Tag, Loading, ErrorBox, useLoad, PrintButtons, usePrintVariant } from './ui'
import InvoiceLines from './InvoiceLines'
import RangePicker, { useRanges, rangeDates } from './RangePicker'

const TYPE = { TAX: 'Tax invoice', PRO: 'Proforma invoice' }
const PLURAL = { TAX: 'invoices', PRO: 'proformas' }

/** Status tag for a row of the invoice list (or a detail with received). */
export function StatusTag({ v }) {
  if (v.status === 'CANCELLED') return <Tag kind="bad">Cancelled</Tag>
  if (v.doc_type === 'PRO') return v.converted_to ? <Tag kind="ok">Converted</Tag> : <Tag>Open</Tag>
  const bal = v.total - (v.received || 0)
  if (bal <= 0.5) return <Tag kind="ok">Settled</Tag>
  return v.received > 0.5 ? <Tag kind="warn">Part paid</Tag> : <Tag>Unpaid</Tag>
}

/** Everything about one invoice or proforma: header, lines, tax, payments. */
export function TransactionDetail({ id, onOpen }) {
  const { api, can } = useAuth()
  const navigate = useNavigate()
  const [variant] = usePrintVariant()
  const [err, setErr] = useState(null)
  const d = useLoad(() => api.invoice(id), [id])
  if (d.loading) return <Loading />
  if (d.error) return <ErrorBox>{d.error}</ErrorBox>

  const x = d.data, inv = x.invoice, t = x.totals, c = x.customer
  const pro = inv.doc_type === 'PRO'
  const dead = inv.status === 'CANCELLED'
  const received = x.received || 0
  const row = { ...inv, total: t.rounded, received }
  const addr = a => [a.addr, a.city, a.pin].filter(Boolean).join(', ')

  return (<div className="tx-detail">
    <div className="tx-title">
      <div>
        <span className="fine">{TYPE[inv.doc_type]}</span>
        <h3 className="mono">{inv.doc_no}</h3>
      </div>
      <div className="tx-amount">
        <span className="fine">Total</span>
        <b className="mono">₹ {inr(t.rounded)}</b>
        <StatusTag v={row} />
      </div>
    </div>

    {dead && <div className="alert bad" style={{ margin: '0 0 12px' }}>Cancelled
      {inv.cancel_reason ? `: ${inv.cancel_reason}` : ''}. It is not counted in sales.</div>}

    <dl className="tx-facts">
      <div><dt>Customer</dt><dd><b>{c.name}</b> <span className="fine mono">{c.code}</span>
        <div className="fine">{addr(c.bill)}</div></dd></div>
      <div><dt>Date</dt><dd className="mono">{gd(inv.doc_date)}</dd></div>
      {!pro && <div><dt>Due</dt><dd className="mono">{gd(inv.due_date)}</dd></div>}
      <div><dt>GSTIN</dt><dd className="mono">{inv.gstin || 'Unregistered'}</dd></div>
      <div><dt>Supply</dt><dd>{t.intra ? 'Intra-state' : 'Inter-state'}</dd></div>
      {inv.po_no && <div><dt>Customer PO</dt><dd className="mono">{inv.po_no}
        {inv.po_date && <span className="fine"> of {gd(inv.po_date)}</span>}</dd></div>}
      {!pro && <div><dt>Received</dt><dd className="mono">₹ {inr(received)}</dd></div>}
      {!pro && !dead && <div><dt>Outstanding</dt>
        <dd className="mono"><b>₹ {inr(Math.max(0, t.rounded - received))}</b></dd></div>}
      {inv.converted_from && <div><dt>Raised from proforma</dt><dd className="mono">{inv.converted_from}</dd></div>}
      {inv.converted_to && <div><dt>Converted to</dt><dd className="mono">{inv.converted_to}</dd></div>}
      {inv.subject && <div className="wide"><dt>Subject</dt><dd>{inv.subject}</dd></div>}
    </dl>

    <InvoiceLines id={id} data={x} />

    <div className="tx-actions">
      <PrintButtons kind="invoices" id={id} variant={variant} onError={setErr} />
      {can('invoice') && !dead && <button type="button" className="btn btn-sm"
        onClick={() => navigate(`/invoices/new?edit=${id}`)}>Edit</button>}
      {onOpen && inv.converted_to_id && <button type="button" className="btn btn-sm"
        onClick={() => onOpen(inv.converted_to_id)}>Open {inv.converted_to}</button>}
      {onOpen && inv.converted_from_id && <button type="button" className="btn btn-sm"
        onClick={() => onOpen(inv.converted_from_id)}>Open proforma {inv.converted_from}</button>}
      {err && <span className="err">{err}</span>}
    </div>
  </div>)
}

/** A modal showing one transaction. */
export function TransactionModal({ id, onClose, backLabel, onBack }) {
  const [cur, setCur] = useState(id)
  useEffect(() => setCur(id), [id])
  useEsc(onClose)
  return (<div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <div className="modal tx" role="dialog" aria-modal="true" aria-label="Transaction">
      <div className="modal-hd">
        {onBack ? <button type="button" className="btn btn-sm" onClick={onBack}>‹ {backLabel || 'Back'}</button>
          : <h2>Transaction</h2>}
        <button type="button" className="rm" aria-label="Close" onClick={onClose}>×</button>
      </div>
      <div className="modal-bd"><TransactionDetail id={cur} onOpen={setCur} /></div>
    </div>
  </div>)
}

function useEsc(fn) {
  useEffect(() => {
    const h = e => { if (e.key === 'Escape') fn() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [fn])
}

/**
 * All invoices (docType TAX) or proformas (PRO) of one customer, filtered by
 * period and status, with totals. Selecting a row opens its details in place.
 */
export function CustomerTransactions({ customer, docType, onClose }) {
  const { api } = useAuth()
  const ranges = useRanges()
  // v5.0: opens on the year chosen at the top, and follows it
  const fyRange = useFyRange()
  const [period, setPeriod] = useState(fyRange)
  useEffect(() => { setPeriod(fyRange) }, [fyRange.key]) // eslint-disable-line
  const [status, setStatus] = useState('LIVE')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)
  const list = useLoad(() => api.invoices(docType, { customerId: customer.id }), [customer.id, docType])
  useEsc(() => (open ? setOpen(null) : onClose()))

  const { start, end } = rangeDates(period, ranges)
  const rows = useMemo(() => (list.data || []).filter(v => {
    if (start && v.doc_date < start) return false
    if (end && v.doc_date > end) return false
    if (status === 'LIVE' && v.status === 'CANCELLED') return false
    if (status === 'CANCELLED' && v.status !== 'CANCELLED') return false
    if (status === 'OPEN' && !(v.status !== 'CANCELLED' && (docType === 'PRO'
      ? !v.converted_to : (v.outstanding ?? 0) > 0.5))) return false
    if (q && !`${v.doc_no} ${v.po_no || ''}`.toLowerCase().includes(q.toLowerCase())) return false
    return true
  }), [list.data, start, end, status, q, docType])

  // Cancelled documents are listed when asked for but never added to the totals.
  const counted = rows.filter(v => v.status !== 'CANCELLED')
  const sum = k => counted.reduce((a, v) => a + (v[k] || 0), 0)
  const T = { taxable: sum('taxable'), tax: sum('tax'), total: sum('total'), received: sum('received') }
  const word = PLURAL[docType]
  const periodLabel = period.range === 'all' ? 'all dates'
    : start && end ? `${gd(start)} to ${gd(end)}` : ''

  const sel = { padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }

  return (<div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <div className="modal tx wide" role="dialog" aria-modal="true" aria-labelledby="ctx-title">
      <div className="modal-hd">
        {open ? <button type="button" className="btn btn-sm" onClick={() => setOpen(null)}>
          ‹ Back to {customer.name}’s {word}</button>
          : <h2 id="ctx-title">{customer.name} <span className="fine mono">{customer.code}</span>
            <div className="tx-sub">{docType === 'TAX' ? 'Tax invoices' : 'Proforma invoices'}</div></h2>}
        <button type="button" className="rm" aria-label="Close" onClick={onClose}>×</button>
      </div>

      {open ? <div className="modal-bd"><TransactionDetail id={open} onOpen={setOpen} /></div> : <>
        <div className="tx-filters">
          <RangePicker value={period} onChange={setPeriod} ranges={ranges} allowAll />
          <select value={status} onChange={e => setStatus(e.target.value)} style={sel} aria-label="Status">
            <option value="LIVE">All except cancelled</option>
            <option value="OPEN">{docType === 'PRO' ? 'Not yet converted' : 'Unpaid or part paid'}</option>
            <option value="CANCELLED">Cancelled only</option>
            <option value="ANY">Everything</option>
          </select>
          <input type="search" placeholder="Number or PO" value={q} onChange={e => setQ(e.target.value)}
            style={{ ...sel, width: 150 }} aria-label="Search by number or PO" />
        </div>

        {list.loading ? <div className="modal-bd"><Loading /></div>
          : list.error ? <div className="modal-bd"><ErrorBox>{list.error}</ErrorBox></div> : <>
            <div className="sr-head">
              <div className="sr-period"><span className="fine">Period</span><b>{periodLabel}</b></div>
              <div className="sr-kpi"><span className="fine">{word[0].toUpperCase() + word.slice(1)}</span>
                <b className="mono">{counted.length}</b></div>
              <div className="sr-kpi"><span className="fine">Taxable value</span><b className="mono">{inr(T.taxable)}</b></div>
              <div className="sr-kpi"><span className="fine">GST</span><b className="mono">{inr(T.tax)}</b></div>
              <div className="sr-kpi"><span className="fine">Total</span><b className="mono">{inr(T.total)}</b></div>
              {docType === 'TAX' && <div className="sr-kpi"><span className="fine">Outstanding</span>
                <b className="mono">{inr(T.total - T.received)}</b></div>}
            </div>
            <div className="modal-bd flush">
              {rows.length ? <div className="scroll"><table className="tx-list">
                <thead><tr><th>{docType === 'TAX' ? 'Invoice' : 'Proforma'}</th><th>Date</th><th>PO no</th>
                  <th className="r">Taxable</th><th className="r">GST</th><th className="r">Total</th>
                  {docType === 'TAX' && <th className="r">Received</th>}
                  <th className="c">Status</th></tr></thead>
                <tbody>
                  {rows.map(v => <tr key={v.id} className={`tx-row${v.status === 'CANCELLED' ? ' dead' : ''}`}
                    tabIndex={0} onClick={() => setOpen(v.id)}
                    onKeyDown={e => { if (e.key === 'Enter') setOpen(v.id) }}>
                    <td className="mono"><b>{v.doc_no}</b>
                      {v.converted_to && <div className="fine">became {v.converted_to}</div>}
                      {v.converted_from && <div className="fine">from {v.converted_from}</div>}</td>
                    <td className="mono">{gd(v.doc_date)}</td>
                    <td className="mono">{v.po_no || '—'}</td>
                    <td className="r mono">{inr(v.taxable)}</td>
                    <td className="r mono">{inr(v.tax)}</td>
                    <td className="r mono"><b>{inr(v.total)}</b></td>
                    {docType === 'TAX' && <td className="r mono">{inr(v.received)}</td>}
                    <td className="c"><StatusTag v={v} /></td>
                  </tr>)}
                  <tr className="sr-total"><td colSpan={3}>Total of {counted.length} {word}
                    {rows.length !== counted.length && <span className="fine"> (cancelled not added)</span>}</td>
                    <td className="r mono">{inr(T.taxable)}</td><td className="r mono">{inr(T.tax)}</td>
                    <td className="r mono">{inr(T.total)}</td>
                    {docType === 'TAX' && <td className="r mono">{inr(T.received)}</td>}<td /></tr>
                </tbody>
              </table></div> : <div className="tx-empty">No {word} for {customer.name} match these filters.</div>}
            </div>
            <div className="tx-foot fine">Select a row to see the document in full.</div>
          </>}
      </>}
    </div>
  </div>)
}
