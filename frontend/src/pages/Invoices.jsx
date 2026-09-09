import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons } from '../components/ui'
import { inr, gd } from '../lib/fmt'

export default function Invoices() {
  const { api, me } = useAuth()
  const list = useLoad(() => api.invoices())
  const [filter, setFilter] = useState('ALL')
  const [flash, showFlash] = useFlash()
  const [variant, setVariant] = usePrintVariant()
  const [printAs, setPrintAs] = useState('')   // '' = as the document is, 'PRO' = proforma layout

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  const rows = list.data.filter(v =>
    filter === 'ALL' ? true
    : filter === 'OPEN' ? v.doc_type === 'TAX' && v.status === 'ACTIVE' && v.outstanding > 0.5
    : filter === 'CANCELLED' ? v.status === 'CANCELLED'
    : v.doc_type === filter && v.status === 'ACTIVE')

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
  async function remove(id) {
    try { await api.delInvoice(id); list.reload() }
    catch (x) { showFlash(x.message, 'bad') }
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
    <Panel title={`Invoice register — ${rows.length}`} right={<>
      <VariantPicker value={variant} onChange={setVariant} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <span className="fine">Print as</span>
        <select value={printAs} onChange={e => setPrintAs(e.target.value)}
          style={{ padding: '6px 9px', border: '1px solid var(--line2)', borderRadius: 7 }}>
          <option value="">As recorded</option>
          <option value="PRO">Proforma invoice</option>
          <option value="TAX">Tax invoice</option>
        </select></label>
      <select value={filter} onChange={e => setFilter(e.target.value)}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="ALL">All documents</option>
        <option value="TAX">Tax invoices only</option>
        <option value="PRO">Proforma only</option>
        <option value="OPEN">Unpaid or part paid</option>
        <option value="CANCELLED">Cancelled</option>
      </select></>} bodyless>
      <Table head={[{ label: 'Type', align: 'c' }, 'Invoice', 'Date', 'Customer', 'PO no',
        { label: 'Supply', align: 'c' }, { label: 'Taxable', align: 'r' },
        { label: 'Tax', align: 'r' }, { label: 'Total', align: 'r' },
        { label: 'Received', align: 'r' }, { label: 'Status', align: 'c' },
        { label: 'Actions', align: 'c' }, '']} empty="Nothing to show.">
        {rows.map(v => {
          const pro = v.doc_type === 'PRO'
          const bal = (v.outstanding ?? 0)
          const dead = v.status === 'CANCELLED'
          return (<tr key={v.id} style={dead ? { opacity: .6 } : undefined}>
            <td className="c">{pro ? <Tag kind="warn">PRO</Tag> : <Tag kind="ok">TAX</Tag>}</td>
            <td className="mono"><b>{v.doc_no}</b></td>
            <td className="mono">{gd(v.doc_date)}</td>
            <td>{v.customer}</td>
            <td className="mono">{v.po_no || '—'}</td>
            <td className="c">{v.intra ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>}</td>
            <td className="r mono">{inr(v.taxable)}</td>
            <td className="r mono">{inr(v.tax)}</td>
            <td className="r mono"><b>{inr(v.total)}</b></td>
            <td className="r mono">{pro ? '—' : inr(v.received)}</td>
            <td className="c">{dead ? <Tag kind="bad" title={v.cancel_reason}>Cancelled</Tag>
              : pro ? <Tag>Proforma</Tag>
              : bal <= 0.5 ? <Tag kind="ok">Settled</Tag>
              : v.received > 0.5 ? <Tag kind="warn">Part paid</Tag> : <Tag>Unpaid</Tag>}</td>
            <td className="c" style={{ whiteSpace: 'nowrap' }}>
              <PrintButtons kind="invoices" id={v.id} variant={variant}
                extra={printAs ? `&as=${printAs}` : ''} onError={m => showFlash(m, 'bad')} />
              <button className="btn btn-sm" style={{ marginLeft: 5 }} onClick={() => mail(v)}>Email</button>
              {pro && !dead && <button className="btn btn-sm btn-a" style={{ marginLeft: 5 }}
                onClick={() => convert(v.id)}>Convert</button>}
              {!pro && !dead && <button className="btn btn-sm" style={{ marginLeft: 5, color: 'var(--red)' }}
                title="Cancel: reverses GST, receipts and TDS, restores stock; the number stays on file"
                onClick={() => cancel(v)}>Cancel</button>}</td>
            <td className="r">{pro && <button className="rm" title="Delete proforma"
              onClick={() => remove(v.id)}>×</button>}</td>
          </tr>)})}
      </Table>
    </Panel>
  </>)
}
