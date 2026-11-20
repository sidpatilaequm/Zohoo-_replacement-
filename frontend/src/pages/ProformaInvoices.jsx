import { Fragment, useEffect, useState } from 'react'
import { useFy } from '../lib/fy'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons, FinancialYearPicker } from '../components/ui'
import { inr, gd, today } from '../lib/fmt'
import EmailComposer from '../components/EmailComposer'
import InvoiceLines from '../components/InvoiceLines'

/** Every proforma raised, including those already converted. Converting raises a
 *  new tax invoice in the invoice number range and leaves the proforma here,
 *  marked with the tax invoice it became. */
export default function ProformaInvoices() {
  const { api, can } = useAuth()
  const navigate = useNavigate()
  const list = useLoad(() => api.invoices('PRO'))
  const [filter, setFilter] = useState('ALL')
  // v5.0: opens on the year chosen at the top, and follows it
  const top = useFy()
  const [fyPick, setFy] = useState(undefined)
  useEffect(() => { setFy(undefined) }, [top.param])
  const fy = fyPick === undefined ? top.param : fyPick
  const fyNorm = fy ? fy.replace(/^FY\s*/i, '') : ''
  const deletedList = useLoad(() => api.deletedInvoices('PRO', fyNorm), [fyNorm])
  const [flash, showFlash] = useFlash()
  const [variant, setVariant] = usePrintVariant()
  const [mailing, setMailing] = useState(null)
  const [converting, setConverting] = useState(null)   // { v, date, no }
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(null)       // proforma whose lines are shown
  const [cvNext, setCvNext] = useState(null)           // next tax invoice number for that date
  const [cvCheck, setCvCheck] = useState(null)         // check of a typed number

  // The tax invoice number the series would give on the chosen date, and
  // whether a typed one is free in that financial year.
  const cvDate = converting?.date, cvNo = (converting?.no || '').trim()
  useEffect(() => {
    setCvNext(null)
    if (!cvDate) return
    let alive = true
    api.invoiceNextNo('TAX', cvDate).then(r => { if (alive) setCvNext(r) }).catch(() => {})
    return () => { alive = false }
  }, [cvDate, api])
  useEffect(() => {
    setCvCheck(null)
    if (!cvNo || !cvDate) return
    let alive = true
    const timer = setTimeout(() => api.checkInvoiceNo('TAX', cvNo, cvDate)
      .then(r => { if (alive) setCvCheck(r) }).catch(() => {}), 300)
    return () => { alive = false; clearTimeout(timer) }
  }, [cvNo, cvDate, api])
  const cvTaken = cvCheck && cvCheck.doc_no === cvNo && !cvCheck.available

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  const currentFyStr = top.current     // follows the company's own year start

  const rawYears = Array.from(new Set([
    ...top.years.map(y => y.label),
    ...(list.data || []).map(v => v.fy).filter(Boolean)
  ])).sort().reverse()
  const years = rawYears.map(y => ({ label: y, current: y === currentFyStr }))

  const inFy = list.data.filter(v => !fyNorm || (v.fy && v.fy.replace(/^FY\s*/i, '') === fyNorm))

  const rows = inFy.filter(v =>
    filter === 'OPEN' ? !v.converted_to : filter === 'DONE' ? !!v.converted_to : true)
  const open = inFy.filter(v => !v.converted_to)
  const canEdit = can('invoice')
  const anyDisc = rows.some(v => v.discount > 0.004)

  async function convert() {
    setBusy(true)
    try {
      const d = await api.convert(converting.v.id, converting.date, cvNo || undefined)
      showFlash(`${converting.v.doc_no} converted to tax invoice ${d.doc_no}. The proforma is kept here.`)
      setConverting(null); list.reload()
    } catch (x) { showFlash(x.message, 'bad') } finally { setBusy(false) }
  }
  async function reconvert(v) {
    if (!window.confirm(`Reconvert ${v.doc_no} to ${v.converted_to}?\n\nThis will override the existing tax invoice (${v.converted_to}) with the latest lines, items, and totals from this proforma.`)) return
    try {
      const d = await api.convert(v.id, undefined, undefined, true)
      showFlash(`${v.doc_no} reconverted. ${d.doc_no} has been updated with the latest details.`)
      list.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }
  async function remove(v) {
    const reason = window.prompt(`Delete proforma ${v.doc_no}? State the reason for deletion (saved to audit history):`)
    if (reason === null) return
    if (reason.trim().length < 3) {
      showFlash('A reason of at least 3 characters is needed to delete.', 'bad')
      return
    }
    try {
      await api.delInvoice(v.id, reason.trim())
      showFlash(`${v.doc_no} deleted and archived to history.`)
      list.reload()
      deletedList.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }

  return (<>
    {flash}
    {mailing && <EmailComposer kind="invoice" id={mailing.id} variant={variant}
      onClose={() => setMailing(null)}
      onSent={r => showFlash(`${r.doc_no} emailed to ${r.to.join(', ')}.`)} />}
    {converting && <div className="modal-bg" onMouseDown={e => {
        if (e.target === e.currentTarget && !busy) setConverting(null) }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="cv-title" style={{ maxWidth: 460 }}>
        <div className="modal-hd"><h2 id="cv-title">Convert {converting.v.doc_no} to a tax invoice</h2>
          <button className="rm" aria-label="Close" onClick={() => setConverting(null)}>×</button></div>
        <div className="modal-bd">
          <p style={{ margin: '0 0 12px' }}>A new tax invoice for <b>{converting.v.customer}</b>,{' '}
            ₹ {inr(converting.v.total)}, is raised in the invoice number range with the same lines,
            and counts towards GST from its date. The proforma stays on this register.</p>
          <div className="f"><label htmlFor="cv-date">Tax invoice date</label>
            <input id="cv-date" type="date" value={converting.date} autoFocus
              onChange={e => setConverting(c => ({ ...c, date: e.target.value }))} /></div>
          <div className="f"><label htmlFor="cv-no">Tax invoice number</label>
            <input id="cv-no" className="mono" maxLength={40} value={converting.no || ''}
              placeholder={cvNext?.doc_no || 'automatic'}
              style={cvTaken ? { borderColor: 'var(--red)' } : undefined}
              onChange={e => setConverting(c => ({ ...c, no: e.target.value }))} />
            <div className="hint">{cvTaken
              ? <span style={{ color: 'var(--red)' }}>Already used in FY {cvCheck.fy}</span>
              : cvNo ? (cvCheck && cvCheck.doc_no === cvNo ? `Free in FY ${cvCheck.fy}` : 'Checking…')
              : `Blank takes the next in the series${cvNext ? ` · FY ${cvNext.fy}` : ''}`}</div></div>
          <div className="ft">
            <button className="btn btn-a" disabled={busy || !converting.date || cvTaken} onClick={convert}>
              {busy ? 'Converting…' : 'Raise tax invoice'}</button>
            <button className="btn" onClick={() => setConverting(null)} disabled={busy}>Cancel</button>
          </div>
        </div>
      </div>
    </div>}
    <Panel title={filter === 'DELETED' ? `Deleted proforma history — ${(deletedList.data || []).length}` : `Proforma register — ${rows.length}`} right={<>
      <span className="fine">{open.length} open · ₹ {inr(open.reduce((a, v) => a + v.total, 0))}</span>
      <VariantPicker value={variant} onChange={setVariant} />
      <FinancialYearPicker value={fy} onChange={setFy} years={years} />
      <select value={filter} onChange={e => { setFilter(e.target.value); setExpanded(null) }}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="ALL">All proformas</option>
        <option value="OPEN">Not yet converted</option>
        <option value="DONE">Converted to tax invoice</option>
        <option value="DELETED">Deleted history</option>
      </select>
      {canEdit && <Link className="btn btn-sm btn-a" to="/invoices/new?type=PRO">New proforma</Link>}
      </>} bodyless>
      {filter === 'DELETED' ? (
        deletedList.loading ? <Loading /> :
        deletedList.error ? <ErrorBox>{deletedList.error}</ErrorBox> :
        <Table head={['Proforma', 'Date', 'Customer', 'PO no',
          { label: 'Taxable', align: 'r' }, { label: 'Tax', align: 'r' }, { label: 'Total', align: 'r' },
          'Deleted by', 'Deleted on', 'Reason', { label: 'Actions', align: 'c' }]}
          empty="No deleted proformas in history.">
          {(deletedList.data || []).map(v => (
            <Fragment key={v.id}>
              <tr style={{ opacity: .85 }}>
                <td className="mono"><b>{v.doc_no}</b><div className="fine">FY {v.fy}</div></td>
                <td className="mono">{gd(v.doc_date)}</td>
                <td><b>{v.customer}</b>{v.customer_gstin && <div className="fine mono">{v.customer_gstin}</div>}</td>
                <td className="mono">{v.po_no || '—'}</td>
                <td className="r mono">{inr(v.taxable)}</td>
                <td className="r mono">{inr(v.tax)}</td>
                <td className="r mono"><b>{inr(v.total)}</b></td>
                <td><b>{v.deleted_by}</b></td>
                <td className="mono fine">{v.deleted_at ? gd(v.deleted_at.slice(0, 10)) + ' ' + v.deleted_at.slice(11, 16) : '—'}</td>
                <td style={{ maxWidth: 220 }} title={v.reason}><Tag kind="bad">Deleted</Tag> <span className="fine">{v.reason}</span></td>
                <td className="c">
                  <button className={`btn btn-sm${expanded === v.id ? ' on' : ''}`}
                    onClick={() => setExpanded(expanded === v.id ? null : v.id)}>
                    {expanded === v.id ? 'Hide items' : `Items (${v.snapshot?.lines?.length ?? 0})`}
                  </button>
                </td>
              </tr>
              {expanded === v.id && (
                <tr className="lines-row">
                  <td colSpan={11}>
                    <div style={{ padding: '12px 16px', background: 'var(--panel-subtle, rgba(0,0,0,0.03))', borderRadius: 6 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
                        <div>
                          <b>Snapshot of {v.doc_no}</b>
                          <span className="fine" style={{ marginLeft: 10 }}>Customer code: {v.customer_code || '—'}</span>
                        </div>
                        <div className="fine">
                          Deleted by <b>{v.deleted_by}</b> on {v.deleted_at ? gd(v.deleted_at.slice(0, 10)) + ' ' + v.deleted_at.slice(11, 16) : '—'} &bull; Reason: <i>{v.reason}</i>
                        </div>
                      </div>
                      {v.snapshot?.lines && v.snapshot.lines.length > 0 ? (
                        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', marginTop: 8 }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid var(--line2)', color: 'var(--muted)', textAlign: 'left' }}>
                              <th style={{ padding: '5px 8px' }}>#</th>
                              <th style={{ padding: '5px 8px' }}>Item</th>
                              <th style={{ padding: '5px 8px' }}>HSN</th>
                              <th style={{ padding: '5px 8px', textAlign: 'right' }}>Qty</th>
                              <th style={{ padding: '5px 8px', textAlign: 'right' }}>Price</th>
                              <th style={{ padding: '5px 8px', textAlign: 'right' }}>Tax %</th>
                              <th style={{ padding: '5px 8px', textAlign: 'right' }}>Line total</th>
                            </tr>
                          </thead>
                          <tbody>
                            {v.snapshot.lines.map((l, idx) => (
                              <tr key={idx} style={{ borderBottom: '1px solid var(--line)' }}>
                                <td style={{ padding: '5px 8px' }}>{l.line_no || idx + 1}</td>
                                <td style={{ padding: '5px 8px' }}>
                                  <b>{l.material_code}</b> {l.material_name}
                                  {l.descr2 && <div className="fine">{l.descr2}</div>}
                                </td>
                                <td style={{ padding: '5px 8px' }} className="mono">{l.hsn || '—'}</td>
                                <td style={{ padding: '5px 8px', textAlign: 'right' }} className="mono">{l.qty}</td>
                                <td style={{ padding: '5px 8px', textAlign: 'right' }} className="mono">₹ {inr(l.price)}</td>
                                <td style={{ padding: '5px 8px', textAlign: 'right' }} className="mono">
                                  {l.igst_pct != null ? `${l.igst_pct}%` : `${(l.cgst_pct || 0) + (l.sgst_pct || 0)}%`}
                                </td>
                                <td style={{ padding: '5px 8px', textAlign: 'right' }} className="mono">
                                  ₹ {inr((l.qty * l.price) - (l.disc_value || 0))}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : <div className="fine">No item lines in snapshot.</div>}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </Table>
      ) : (
      <Table head={['Proforma', 'Date', 'Customer', 'PO no', { label: 'Supply', align: 'c' },
        ...(anyDisc ? [{ label: 'Discount', align: 'r' }] : []),
        { label: 'Taxable', align: 'r' }, { label: 'Tax', align: 'r' }, { label: 'Total', align: 'r' },
        { label: 'Status', align: 'c' }, { label: 'Actions', align: 'c' }, '']}
        empty="No proformas yet. Raise one from Customer Invoices with Document type set to Proforma invoice.">
        {rows.map(v => (<Fragment key={v.id}><tr>
          <td className="mono"><b>{v.doc_no}</b>
            <div className="fine">FY {v.fy}</div></td>
          <td className="mono">{gd(v.doc_date)}</td>
          <td>{v.customer}</td>
          <td className="mono">{v.po_no || '—'}</td>
          <td className="c">{v.intra ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>}</td>
          {anyDisc && <td className="r mono">{v.discount > 0.004 ? inr(v.discount) : '—'}</td>}
          <td className="r mono">{inr(v.taxable)}</td>
          <td className="r mono">{inr(v.tax)}</td>
          <td className="r mono"><b>{inr(v.total)}</b></td>
          <td className="c">{v.converted_to
            ? <><Tag kind="ok">Converted</Tag>
                <div className="fine mono">{v.converted_to}{v.converted_on ? `, ${gd(v.converted_on)}` : ''}</div></>
            : <Tag kind="warn">Open</Tag>}</td>
          <td className="c" style={{ whiteSpace: 'nowrap' }}>
            <button className={`btn btn-sm${expanded === v.id ? ' on' : ''}`} style={{ marginRight: 5 }}
              aria-expanded={expanded === v.id}
              onClick={() => setExpanded(expanded === v.id ? null : v.id)}>
              Items ({v.lines_count})</button>
            <PrintButtons kind="invoices" id={v.id} variant={variant} onError={m => showFlash(m, 'bad')} />
            <button className="btn btn-sm" style={{ marginLeft: 5 }} onClick={() => setMailing(v)}>Email</button>
            <button className="btn btn-sm" style={{ marginLeft: 5 }}
              onClick={() => navigate(`/invoices/new?edit=${v.id}`)}>Edit</button>
            {canEdit && !v.converted_to && <button className="btn btn-sm btn-a" style={{ marginLeft: 5 }}
              onClick={() => setConverting({ v, date: today() })}>Convert to tax invoice</button>}
            {canEdit && v.converted_to && <button className="btn btn-sm btn-a" style={{ marginLeft: 5 }}
              title={`Override ${v.converted_to} with latest proforma details`}
              onClick={() => reconvert(v)}>Reconvert to tax invoice</button>}</td>
          <td className="r">{canEdit && !v.converted_to && <button className="rm" title="Delete proforma"
            aria-label={`Delete ${v.doc_no}`} onClick={() => remove(v)}>×</button>}</td>
        </tr>
        {expanded === v.id && <tr className="lines-row"><td colSpan={anyDisc ? 12 : 11}>
          <InvoiceLines id={v.id} /></td></tr>}
        </Fragment>))}
      </Table>
      )}
    </Panel>
  </>)
}
