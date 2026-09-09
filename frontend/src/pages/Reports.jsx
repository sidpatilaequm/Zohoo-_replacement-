import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, useLoad, Loading, ErrorBox } from '../components/ui'
import { inr, gd } from '../lib/fmt'
import GstFiling from '../components/GstFiling'

const REPORTS = [
  { key: 'crec', label: 'Customer outstanding — receivables' },
  { key: 'vpay', label: 'Vendor outstanding — payables' },
  { key: 'marg', label: 'Margin by material' },
  { key: 'gst',  label: 'GST filing — GSTR-1 (A), GSTR-3B (B), A − B' },
]

export default function Reports() {
  const { api } = useAuth()
  const [kind, setKind] = useState('crec')
  const rec = useLoad(() => api.receivables())
  const pay = useLoad(() => api.payables())
  const mar = useLoad(() => api.margin())
  const busy = rec.loading || pay.loading || mar.loading
  if (busy) return <Loading />
  const anyErr = rec.error || pay.error || mar.error
  if (anyErr) return <ErrorBox>{anyErr}</ErrorBox>

  function csv(rows, head, file) {
    const body = [head.join(','), ...rows.map(r => r.map(v =>
      `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob([body], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = file; a.click()
    URL.revokeObjectURL(url)
  }
  const download = () => {
    if (kind === 'crec') csv((rec.data || []).map(r => [r.customer, r.doc_no, gd(r.doc_date),
      gd(r.due_date), r.total, r.received, r.outstanding]),
      ['Customer', 'Invoice', 'Date', 'Due', 'Total', 'Received', 'Outstanding'], 'receivables.csv')
    else if (kind === 'vpay') csv((pay.data || []).map(r => [r.vendor, r.doc_no, gd(r.doc_date),
      gd(r.due_date), r.total, r.paid, r.outstanding]),
      ['Vendor', 'Invoice', 'Date', 'Due', 'Total', 'Paid', 'Outstanding'], 'payables.csv')
    else csv((mar.data || []).map(r => [r.code, r.descr, r.sold_qty, r.sales_value,
      r.bought_qty, r.purchase_value, r.margin, r.margin_pct]),
      ['Material', 'Description', 'Sold qty', 'Sales value', 'Bought qty',
       'Purchase value', 'Margin', 'Margin %'], 'margin.csv')
  }

  const picker = (
    <select value={kind} onChange={e => setKind(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      {REPORTS.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
    </select>)

  if (kind === 'gst') return (<>
    <Panel title="Reports" right={picker}>
      <span className="fine">GSTR-1 is built from the tax invoices on file (cancelled ones excluded and
        reported in table 13) and downloads in the portal's upload formats. Upload the GSTR-3B you filed
        and the third panel shows A − B head by head.</span>
    </Panel>
    <GstFiling />
  </>)

  return (
    <Panel title="Reports" right={<>
      {picker}
      <button className="btn btn-sm" onClick={download}>Export CSV</button></>} bodyless>

      {kind === 'crec' && (
        <Table head={['Customer', 'Invoice', 'Date', 'Due', { label: 'Total', align: 'r' },
          { label: 'Received', align: 'r' }, { label: 'Outstanding', align: 'r' }]}
          empty="Nothing outstanding.">
          {(rec.data || []).map(r => (
            <tr key={r.doc_no}><td>{r.customer}</td><td className="mono">{r.doc_no}</td>
              <td className="mono">{gd(r.doc_date)}</td><td className="mono">{gd(r.due_date)}</td>
              <td className="r mono">{inr(r.total)}</td><td className="r mono">{inr(r.received)}</td>
              <td className="r mono"><b>{inr(r.outstanding)}</b></td></tr>))}
        </Table>)}

      {kind === 'vpay' && (
        <Table head={['Vendor', 'Invoice', 'Date', 'Due', { label: 'Total', align: 'r' },
          { label: 'Paid', align: 'r' }, { label: 'Outstanding', align: 'r' }]}
          empty="Nothing outstanding.">
          {(pay.data || []).map(r => (
            <tr key={r.doc_no}><td>{r.vendor}</td><td className="mono">{r.doc_no}</td>
              <td className="mono">{gd(r.doc_date)}</td><td className="mono">{gd(r.due_date)}</td>
              <td className="r mono">{inr(r.total)}</td><td className="r mono">{inr(r.paid)}</td>
              <td className="r mono"><b>{inr(r.outstanding)}</b></td></tr>))}
        </Table>)}

      {kind === 'marg' && (
        <Table head={['Material', 'Description', { label: 'Sold', align: 'r' },
          { label: 'Sales value', align: 'r' }, { label: 'Bought', align: 'r' },
          { label: 'Purchase value', align: 'r' }, { label: 'Margin', align: 'r' },
          { label: 'Margin %', align: 'r' }]} empty="No movement yet.">
          {(mar.data || []).map(r => (
            <tr key={r.code}><td className="mono"><b>{r.code}</b></td><td>{r.descr}</td>
              <td className="r mono">{r.sold_qty}</td><td className="r mono">{inr(r.sales_value)}</td>
              <td className="r mono">{r.bought_qty}</td><td className="r mono">{inr(r.purchase_value)}</td>
              <td className="r mono" style={r.margin < 0 ? { color: 'var(--red)' } : {}}>
                <b>{inr(r.margin)}</b></td>
              <td className="r mono">{r.margin_pct === null ? '—' : r.margin_pct + '%'}</td></tr>))}
        </Table>)}
    </Panel>
  )
}
