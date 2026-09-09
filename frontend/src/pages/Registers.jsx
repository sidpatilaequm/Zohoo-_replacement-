import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons } from '../components/ui'
import { inr, money, gd } from '../lib/fmt'

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const label = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }

export default function Registers() {
  const { api } = useAuth()
  const periods = useLoad(() => api.periods())
  const [period, setPeriod] = useState('')
  const [which, setWhich] = useState('invoices')
  const [variant, setVariant] = usePrintVariant()
  const [printAs, setPrintAs] = useState('')
  const [flash, showFlash] = useFlash()
  const p = period || null
  const inv = useLoad(() => api.invoiceRegister(p), [p])
  const gst = useLoad(() => api.gstRegister(p), [p])
  const tds = useLoad(() => api.tdsRegister(p), [p])

  if (periods.loading) return <Loading />
  const busy = inv.loading || gst.loading || tds.loading
  const anyErr = inv.error || gst.error || tds.error
  if (anyErr) return <ErrorBox>{anyErr}</ErrorBox>

  const controls = (<>
    <select value={which} onChange={e => setWhich(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      <option value="invoices">Invoice register</option>
      <option value="gst">GST register</option>
      <option value="tds">TDS register</option>
    </select>
    <select value={period} onChange={e => setPeriod(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      <option value="">All periods</option>
      {(periods.data || []).map(x => <option key={x} value={x}>{label(x)}</option>)}
    </select>
    <a className="btn btn-sm" href={api.registerCsv(which, p)}>Export CSV</a></>)

  if (busy) return <><Panel title="Registers" right={controls} /><Loading /></>

  return (<>
    {flash}
    <Panel title="Registers" right={controls}>
      <Alert kind="ok">These are the books as recorded here. They are the starting point for a
        return, not the return itself.</Alert>
    </Panel>

    {which === 'invoices' && (
      <Panel title={`Invoice register — ${inv.data.length} documents`} right={<>
        <VariantPicker value={variant} onChange={setVariant} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <span className="fine">Print as</span>
          <select value={printAs} onChange={e => setPrintAs(e.target.value)}
            style={{ padding: '6px 9px', border: '1px solid var(--line2)', borderRadius: 7 }}>
            <option value="">As recorded</option>
            <option value="PRO">Proforma invoice</option>
            <option value="TAX">Tax invoice</option>
          </select></label></>} bodyless>
        <Table head={[{ label: 'Type', align: 'c' }, 'Invoice', 'Date', 'Customer', 'GSTIN',
          'PAN', { label: 'MSME', align: 'c' }, { label: 'Supply', align: 'c' },
          { label: 'Taxable', align: 'r' }, { label: 'CGST', align: 'r' },
          { label: 'SGST', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'Total', align: 'r' }, { label: 'Outstanding', align: 'r' },
          { label: 'Print', align: 'c' }]}
          empty="Nothing in this period.">
          {inv.data.map((r, i) => (
            <tr key={i} style={r.status === 'CANCELLED' ? { opacity: .6 } : undefined}>
              <td className="c">{r.status === 'CANCELLED'
                ? <Tag kind="bad" title={r.cancel_reason}>CANCELLED</Tag>
                : r.doc_type === 'Proforma'
                ? <Tag kind="warn">PRO</Tag> : <Tag kind="ok">TAX</Tag>}</td>
              <td className="mono"><b>{r.doc_no}</b></td>
              <td className="mono">{gd(r.doc_date)}</td>
              <td>{r.customer}<div className="fine mono">{r.customer_code}</div></td>
              <td className="mono">{r.gstin || '—'}</td>
              <td className="mono">{r.pan || '—'}</td>
              <td className="c">{r.msme ? <Tag kind="ok">Yes</Tag> : <Tag>No</Tag>}</td>
              <td className="c">{r.supply === 'Intra-state'
                ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>}</td>
              <td className="r mono">{inr(r.taxable)}</td>
              <td className="r mono">{inr(r.cgst)}</td><td className="r mono">{inr(r.sgst)}</td>
              <td className="r mono">{inr(r.igst)}</td>
              <td className="r mono"><b>{inr(r.total)}</b></td>
              <td className="r mono">{r.outstanding === null || r.status === 'CANCELLED' ? '—' : inr(r.outstanding)}</td>
              <td className="c"><PrintButtons kind="invoices" id={r.id} variant={variant}
                extra={printAs ? `&as=${printAs}` : ''} onError={m => showFlash(m, 'bad')} /></td>
            </tr>))}
        </Table>
      </Panel>)}

    {which === 'gst' && (<>
      <Panel title="GST register — position" bodyless>
        <Table head={['', { label: 'Taxable', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]}>
          <tr><td>Outward supplies</td>
            <td className="r mono">{inr(gst.data.totals.outward.taxable)}</td>
            <td className="r mono">{inr(gst.data.totals.outward.igst)}</td>
            <td className="r mono">{inr(gst.data.totals.outward.cgst)}</td>
            <td className="r mono">{inr(gst.data.totals.outward.sgst)}</td></tr>
          <tr><td>Input tax credit</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.taxable)}</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.igst)}</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.cgst)}</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.sgst)}</td></tr>
          <tr style={{ background: 'var(--accent-soft)' }}>
            <td><b>Net payable</b></td><td className="r mono">—</td>
            <td className="r mono"><b>{inr(gst.data.totals.net_payable.igst)}</b></td>
            <td className="r mono"><b>{inr(gst.data.totals.net_payable.cgst)}</b></td>
            <td className="r mono"><b>{inr(gst.data.totals.net_payable.sgst)}</b></td></tr>
        </Table>
        <div className="panel-bd"><Alert kind="warn">{gst.data.note}</Alert></div>
      </Panel>
      <Panel title={`Outward — ${gst.data.outward.length}`} bodyless>
        <Table head={['Document', 'Date', 'Party', 'GSTIN', { label: 'Section', align: 'c' },
          { label: 'Taxable', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]} empty="Nothing outward.">
          {gst.data.outward.map((r, i) => (
            <tr key={i}><td className="mono"><b>{r.doc_no}</b></td>
              <td className="mono">{gd(r.doc_date)}</td><td>{r.party}</td>
              <td className="mono">{r.gstin || '—'}</td>
              <td className="c"><Tag kind={r.section === 'b2b' ? 'ok' : 'warn'}>{r.section}</Tag></td>
              <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.igst)}</td>
              <td className="r mono">{inr(r.cgst)}</td><td className="r mono">{inr(r.sgst)}</td>
            </tr>))}
        </Table>
      </Panel>
      <Panel title={`Inward — ${gst.data.inward.length}`} bodyless>
        <Table head={['Document', 'Date', 'Party', 'GSTIN', { label: 'Credit', align: 'c' },
          { label: 'Taxable', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]} empty="Nothing inward.">
          {gst.data.inward.map((r, i) => (
            <tr key={i}><td className="mono"><b>{r.doc_no}</b></td>
              <td className="mono">{gd(r.doc_date)}</td><td>{r.party}</td>
              <td className="mono">{r.gstin || '—'}</td>
              <td className="c">{r.registered
                ? <Tag kind="ok">claimable</Tag> : <Tag>unregistered</Tag>}</td>
              <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.igst)}</td>
              <td className="r mono">{inr(r.cgst)}</td><td className="r mono">{inr(r.sgst)}</td>
            </tr>))}
        </Table>
      </Panel>
    </>)}

    {which === 'tds' && (
      <Panel title={`TDS register — ${money(tds.data.total_tds)} deducted`} bodyless>
        <Table head={['Payment date', 'Vendor', 'PAN', { label: 'MSME', align: 'c' },
          'Vendor invoice', { label: 'Taxable', align: 'r' }, { label: 'Gross', align: 'r' },
          { label: 'TDS', align: 'r' }, { label: 'Paid', align: 'r' },
          { label: 'Implied rate', align: 'r' }, 'Reference']}
          empty="No tax was deducted in this period.">
          {tds.data.rows.map((r, i) => (
            <tr key={i}>
              <td className="mono">{gd(r.pay_date)}</td>
              <td>{r.vendor}<div className="fine mono">{r.vendor_code}</div></td>
              <td className="mono">{r.pan || <span style={{ color: 'var(--red)' }}>missing</span>}</td>
              <td className="c">{r.msme
                ? <Tag kind="ok">{r.msme_number || 'Yes'}</Tag> : <Tag>No</Tag>}</td>
              <td className="mono">{r.vendor_invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
              <td className="r mono">{inr(r.invoice_taxable)}</td>
              <td className="r mono">{inr(r.gross)}</td>
              <td className="r mono"><b>{inr(r.tds)}</b></td>
              <td className="r mono">{inr(r.paid)}</td>
              <td className="r mono">{r.implied_rate_pct}%</td>
              <td className="mono fine">{r.bank_ref || '—'}</td>
            </tr>))}
        </Table>
        <div className="panel-bd">
          {tds.data.vendors_without_pan.length > 0 && <Alert kind="bad">
            <b>No PAN on file for {tds.data.vendors_without_pan.join(', ')}.</b> Section 206AA
            requires a higher rate where the deductee has not furnished a PAN.</Alert>}
          <Alert kind="warn">{tds.data.note}</Alert>
        </div>
      </Panel>)}
  </>)
}
