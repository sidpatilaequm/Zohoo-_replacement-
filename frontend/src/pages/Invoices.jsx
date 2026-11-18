import { Fragment, useState, useEffect } from 'react'
import { useFy } from '../lib/fy'
import InvoicePayments from '../components/InvoicePayments'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons, FinancialYearPicker } from '../components/ui'
import { inr, gd } from '../lib/fmt'
import DocFiles from '../components/DocFiles'
import InvoiceLines from '../components/InvoiceLines'
import EmailComposer from '../components/EmailComposer'
export default function Invoices() {
  const { api, me, can } = useAuth()
  const navigate = useNavigate()
  const list = useLoad(() => api.invoices('TAX'))
  const [filter, setFilter] = useState('ALL')
  // v5.0: opens on the year chosen at the top, and follows it
  const top = useFy()
  const [fyPick, setFy] = useState(undefined)
  useEffect(() => { setFy(undefined) }, [top.param])
  const fy = fyPick === undefined ? top.param : fyPick
  const fyNorm = fy ? fy.replace(/^FY\s*/i, '') : ''
  const deletedList = useLoad(() => api.deletedInvoices('TAX', fyNorm), [fyNorm])
  const [flash, showFlash] = useFlash()
  const [variant, setVariant] = usePrintVariant()
  const [printAs, setPrintAs] = useState('')   // '' = as the document is, 'PRO' = proforma layout
  const [documentsFor, setDocumentsFor] = useState(null)
  const [open, setOpen] = useState(null)       // invoice whose lines are shown
  const [mailing, setMailing] = useState(null)
  const [paysFor, setPaysFor] = useState(null)      // v5.0: invoice whose payments are open
  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  const canEdit = can ? can('invoice') : true

  const currentFyStr = top.current     // follows the company's own year start

  const rawYears = Array.from(new Set([
    ...top.years.map(y => y.label),
    ...(list.data || []).map(v => v.fy).filter(Boolean)
  ])).sort().reverse()
  const years = rawYears.map(y => ({ label: y, current: y === currentFyStr }))

  const inFy = list.data.filter(v => !fyNorm || (v.fy && v.fy.replace(/^FY\s*/i, '') === fyNorm))

  const rows = inFy.filter(v =>
    filter === 'ALL' ? v.status !== 'CANCELLED'
    : filter === 'OPEN' ? v.status === 'ACTIVE' && v.outstanding > 0.5
    : filter === 'CANCELLED' ? v.status === 'CANCELLED'
    : true)
  const anyDisc = rows.some(v => v.discount > 0.004)

  async function convert(id) {
    try { const d = await api.convert(id); showFlash(`Converted to ${d.doc_no}.`); list.reload() }
    catch (x) { showFlash(x.message, 'bad') }
  }
  async function cancel(v) {
    const reason = window.prompt(`Cancel ${v.doc_no}? Give the reason (kept on the document and shown in GSTR-1 table 13).`)
    if (reason === null) return
    if (reason.trim().length < 3) { showFlash('A reason of at least 3 characters is needed.', 'bad'); return }
    try {
      const d = await api.cancelInvoice(v.id, reason.trim())
      const g = d.gst_reversed
      showFlash(`${d.doc_no} cancelled. GST reversed: ₹${inr(g.igst + g.cgst + g.sgst)}`
        + (d.receipts_reversed.length ? `; ${d.receipts_reversed.length} receipt(s) reversed` : '')
        + (d.tds_reversed ? `; TDS ₹${inr(d.tds_reversed)} reversed` : '')
        + (d.stock_restored.length ? '; stock restored.' : '.'))
      list.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }
  async function remove(v) {
    if (v.status !== 'CANCELLED' && v.received > 0.5) {
      showFlash(`Cannot delete ${v.doc_no} because it has recorded receipts. Please cancel or reverse payments first.`, 'bad')
      return
    }
    const reason = window.prompt(`Delete ${v.doc_no}? State the reason for deletion (saved to audit history):`)
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
  function mail(v) {
    const t = me?.tenant
    const subject = `${v.doc_type === 'PRO' ? 'Proforma invoice' : 'Tax invoice'} ${v.doc_no} from ${t?.name}`
    const body = `Dear ${v.customer},\n\nPlease find ${v.doc_type === 'PRO' ? 'proforma ' : ''}invoice `
      + `${v.doc_no} dated ${gd(v.doc_date)} for ₹ ${inr(v.total)}.\n\nRegards,\n${t?.name}`
    window.location.href = `mailto:${encodeURIComponent(v.customer_email || '')}`
      + `?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
  }

  return (<>
    {flash}
    {mailing && <EmailComposer kind="invoice" id={mailing.id} variant={variant}
      onClose={() => setMailing(null)}
      onSent={r => showFlash(`${r.doc_no} emailed to ${r.to.join(', ')}.`)} />}
    <Panel title={filter === 'DELETED' ? `Deleted invoice history — ${(deletedList.data || []).length}` : `Invoice register — ${rows.length}`} right={<>
      <VariantPicker value={variant} onChange={setVariant} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <span className="fine">Print as</span>
        <select value={printAs} onChange={e => setPrintAs(e.target.value)}
          style={{ padding: '6px 9px', border: '1px solid var(--line2)', borderRadius: 7 }}>
          <option value="">As recorded</option>
          <option value="PRO">Proforma invoice</option>
          <option value="TAX">Tax invoice</option>
        </select></label>
      <FinancialYearPicker value={fy} onChange={setFy} years={years} />
      <select value={filter} onChange={e => { setFilter(e.target.value); setOpen(null) }}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="ALL">All invoices</option>
        <option value="OPEN">Unpaid or part paid</option>
        <option value="CANCELLED">Cancelled</option>
        <option value="DELETED">Deleted history</option>
      </select>
      {canEdit && <Link className="btn btn-sm btn-a" to="/invoices/new">Add invoice</Link>}
    </>} bodyless>
      {filter === 'DELETED' ? (
        deletedList.loading ? <Loading /> :
        deletedList.error ? <ErrorBox>{deletedList.error}</ErrorBox> :
        <Table head={[{ label: 'Type', align: 'c' }, 'Invoice', 'Date', 'Customer', 'PO no',
          { label: 'Taxable', align: 'r' }, { label: 'Tax', align: 'r' }, { label: 'Total', align: 'r' },
          'Deleted by', 'Deleted on', 'Reason', { label: 'Actions', align: 'c' }]}
          empty="No deleted invoices in history.">
          {(deletedList.data || []).map(v => (
            <Fragment key={v.id}>
              <tr style={{ opacity: .85 }}>
                <td className="c">{v.doc_type === 'PRO' ? <Tag kind="warn">PRO</Tag> : <Tag kind="ok">TAX</Tag>}</td>
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
                  <button className={`btn btn-sm${open === v.id ? ' on' : ''}`}
                    onClick={() => setOpen(open === v.id ? null : v.id)}>
                    {open === v.id ? 'Hide items' : `Items (${v.snapshot?.lines?.length ?? 0})`}
                  </button>
                </td>
              </tr>
              {open === v.id && (
                <tr className="lines-row">
                  <td colSpan={12}>
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
      <Table head={[{ label: 'Type', align: 'c' }, 'Invoice', 'Date', 'Customer', 'PO no',
        { label: 'Supply', align: 'c' },
        ...(anyDisc ? [{ label: 'Discount', align: 'r' }] : []),
        { label: 'Taxable', align: 'r' },
        { label: 'Tax', align: 'r' }, { label: 'Total', align: 'r' },
        { label: 'Received', align: 'r' }, { label: 'Status', align: 'c' },
        { label: 'Actions', align: 'c' }, '']} empty="Nothing to show.">
        {rows.map(v => {
          const pro = v.doc_type === 'PRO'
          const bal = (v.outstanding ?? 0)
          const dead = v.status === 'CANCELLED'
          return (<Fragment key={v.id}><tr style={dead ? { opacity: .6 } : undefined}>
            <td className="c">{pro ? <Tag kind="warn">PRO</Tag> : <Tag kind="ok">TAX</Tag>}</td>
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
            <td className="r mono">{pro ? '—' : inr(v.received)}</td>
            <td className="c">{dead ? <Tag kind="bad" title={v.cancel_reason}>Cancelled</Tag>
              : pro ? <Tag>Proforma</Tag>
              : bal <= 0.5 ? <Tag kind="ok">Settled</Tag>
              : v.received > 0.5 ? <Tag kind="warn">Part paid</Tag> : <Tag>Unpaid</Tag>}</td>
            <td className="c" style={{ whiteSpace: 'nowrap' }}>
              <button className={`btn btn-sm${open === v.id ? ' on' : ''}`} style={{ marginRight: 5 }}
                aria-expanded={open === v.id}
                onClick={() => setOpen(open === v.id ? null : v.id)}>
                Items ({v.lines_count})</button>
              <PrintButtons kind="invoices" id={v.id} variant={variant}
                extra={printAs ? `&as=${printAs}` : ''} onError={m => showFlash(m, 'bad')} />
              <button
                  className="btn btn-sm"
                  style={{ marginLeft: 5 }}
                  onClick={() => setDocumentsFor(
                    documentsFor === v.id ? null : v.id
                  )}
                >
                  Docs
                </button>
              {!pro && !dead && <button className="btn btn-sm" style={{ marginLeft: 5 }}
                title="Payments, TDS and GST withheld; attach bank credits"
                onClick={() => setPaysFor(v.id)}>Payments</button>}
              <button className="btn btn-sm" style={{ marginLeft: 5 }} onClick={() => setMailing(v)}>Email</button>
              {!dead && (
                <button className="btn btn-sm" style={{ marginLeft: 5 }}
                  onClick={() => navigate(`/invoices/new?edit=${v.id}`)}>Edit</button>
              )}
              {pro && !dead && <button className="btn btn-sm btn-a" style={{ marginLeft: 5 }}
                onClick={() => convert(v.id)}>Convert</button>}
              {!pro && !dead && <button className="btn btn-sm" style={{ marginLeft: 5, color: 'var(--red)' }}
                title="Cancel: reverses GST, receipts and TDS, restores stock; the number stays on file"
                onClick={() => cancel(v)}>Cancel</button>}
              {canEdit && <button className="btn btn-sm" style={{ marginLeft: 5, color: 'var(--muted)' }}
                title="Delete invoice and archive to history"
                onClick={() => remove(v)}>Delete</button>}</td>
            <td className="r">{canEdit && <button className="rm" title={`Delete ${v.doc_no} (saves to history)`}
              aria-label={`Delete ${v.doc_no}`}
              onClick={() => remove(v)}>×</button>}</td>
          </tr>
          {open === v.id && <tr className="lines-row"><td colSpan={anyDisc ? 14 : 13}>
            <InvoiceLines id={v.id} /></td></tr>}
          </Fragment>)})}
      </Table>
      )}
        </Panel>

    {paysFor && <InvoicePayments linkType="CUST_INV" id={paysFor} onClose={() => setPaysFor(null)}
      onChanged={() => list.reload()} />}
    {documentsFor && (
      <DocFiles
        kind="invoice"
        id={documentsFor}
      />
    )}
  </>)
}
