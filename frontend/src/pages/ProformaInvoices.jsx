import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons } from '../components/ui'
import { inr, gd, today } from '../lib/fmt'
import EmailComposer from '../components/EmailComposer'

/** Every proforma raised, including those already converted. Converting raises a
 *  new tax invoice in the invoice number range and leaves the proforma here,
 *  marked with the tax invoice it became. */
export default function ProformaInvoices() {
  const { api, can } = useAuth()
  const list = useLoad(() => api.invoices('PRO'))
  const [filter, setFilter] = useState('ALL')
  const [flash, showFlash] = useFlash()
  const [variant, setVariant] = usePrintVariant()
  const [mailing, setMailing] = useState(null)
  const [converting, setConverting] = useState(null)   // { v, date }
  const [busy, setBusy] = useState(false)

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  const rows = list.data.filter(v =>
    filter === 'OPEN' ? !v.converted_to : filter === 'DONE' ? !!v.converted_to : true)
  const open = list.data.filter(v => !v.converted_to)
  const canEdit = can('invoice')

  async function convert() {
    setBusy(true)
    try {
      const d = await api.convert(converting.v.id, converting.date)
      showFlash(`${converting.v.doc_no} converted to tax invoice ${d.doc_no}. The proforma is kept here.`)
      setConverting(null); list.reload()
    } catch (x) { showFlash(x.message, 'bad') } finally { setBusy(false) }
  }
  async function remove(v) {
    if (!window.confirm(`Delete proforma ${v.doc_no}? Its number will not be reused.`)) return
    try { await api.delInvoice(v.id); showFlash(`${v.doc_no} deleted.`); list.reload() }
    catch (x) { showFlash(x.message, 'bad') }
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
          <div className="ft">
            <button className="btn btn-a" disabled={busy || !converting.date} onClick={convert}>
              {busy ? 'Converting…' : 'Raise tax invoice'}</button>
            <button className="btn" onClick={() => setConverting(null)} disabled={busy}>Cancel</button>
          </div>
        </div>
      </div>
    </div>}
    <Panel title={`Proforma register — ${rows.length}`} right={<>
      <span className="fine">{open.length} open · ₹ {inr(open.reduce((a, v) => a + v.total, 0))}</span>
      <VariantPicker value={variant} onChange={setVariant} />
      <select value={filter} onChange={e => setFilter(e.target.value)}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="ALL">All proformas</option>
        <option value="OPEN">Not yet converted</option>
        <option value="DONE">Converted to tax invoice</option>
      </select>
      {canEdit && <Link className="btn btn-sm btn-a" to="/invoices/new?type=PRO">New proforma</Link>}
      </>} bodyless>
      <Table head={['Proforma', 'Date', 'Customer', 'PO no', { label: 'Supply', align: 'c' },
        { label: 'Taxable', align: 'r' }, { label: 'Tax', align: 'r' }, { label: 'Total', align: 'r' },
        { label: 'Status', align: 'c' }, { label: 'Actions', align: 'c' }, '']}
        empty="No proformas yet. Raise one from Customer Invoices with Document type set to Proforma invoice.">
        {rows.map(v => (<tr key={v.id}>
          <td className="mono"><b>{v.doc_no}</b></td>
          <td className="mono">{gd(v.doc_date)}</td>
          <td>{v.customer}</td>
          <td className="mono">{v.po_no || '—'}</td>
          <td className="c">{v.intra ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>}</td>
          <td className="r mono">{inr(v.taxable)}</td>
          <td className="r mono">{inr(v.tax)}</td>
          <td className="r mono"><b>{inr(v.total)}</b></td>
          <td className="c">{v.converted_to
            ? <><Tag kind="ok">Converted</Tag>
                <div className="fine mono">{v.converted_to}{v.converted_on ? `, ${gd(v.converted_on)}` : ''}</div></>
            : <Tag kind="warn">Open</Tag>}</td>
          <td className="c" style={{ whiteSpace: 'nowrap' }}>
            <PrintButtons kind="invoices" id={v.id} variant={variant} onError={m => showFlash(m, 'bad')} />
            <button className="btn btn-sm" style={{ marginLeft: 5 }} onClick={() => setMailing(v)}>Email</button>
            {canEdit && !v.converted_to && <button className="btn btn-sm btn-a" style={{ marginLeft: 5 }}
              onClick={() => setConverting({ v, date: today() })}>Convert to tax invoice</button>}</td>
          <td className="r">{canEdit && !v.converted_to && <button className="rm" title="Delete proforma"
            aria-label={`Delete ${v.doc_no}`} onClick={() => remove(v)}>×</button>}</td>
        </tr>))}
      </Table>
    </Panel>
  </>)
}
