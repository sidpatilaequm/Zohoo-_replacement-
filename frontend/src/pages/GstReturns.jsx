import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money } from '../lib/fmt'
import GstFiling from '../components/GstFiling'

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const label = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }

export default function GstReturns() {
  const { api } = useAuth()
  const [flash, showFlash] = useFlash()
  const periods = useLoad(() => api.periods())
  const [period, setPeriod] = useState('')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!period && periods.data?.length) setPeriod(periods.data[0])
  }, [periods.data, period])

  useEffect(() => {
    if (!period) return
    let alive = true
    setErr(null)
    Promise.all([api.gstr1(period), api.gstr3b(period)])
      .then(([g1, g3]) => { if (alive) setData({ g1, g3 }) })
      .catch(e => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [period, api])

  if (periods.loading) return <Loading />
  if (periods.error) return <ErrorBox>{periods.error}</ErrorBox>
  if (!periods.data?.length)
    return <Alert kind="warn">No documents have been saved yet, so there is nothing to file.</Alert>

  const selector = (
    <select value={period} onChange={e => setPeriod(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      {periods.data.map(p => <option key={p} value={p}>{label(p)}</option>)}
    </select>)

  if (err) return <><Panel title="GST returns" right={selector} /><ErrorBox>{err}</ErrorBox></>
  if (!data) return <><Panel title="GST returns" right={selector} /><Loading /></>

  const { g1, g3 } = data
  const section = (key, title, rows) => rows.length ? (
    <div key={key}>
      <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
        color: 'var(--muted)', margin: '16px 0 7px', fontWeight: 500 }}>
        {title} — {rows.length} invoice{rows.length === 1 ? '' : 's'}</h3>
      <Table head={['Invoice', 'Date', 'Recipient', 'GSTIN', 'Place of supply',
        { label: 'Invoice value', align: 'r' }, { label: 'Taxable', align: 'r' },
        { label: 'IGST', align: 'r' }, { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]}>
        {rows.map(r => (
          <tr key={r.doc_no}>
            <td className="mono"><b>{r.doc_no}</b></td><td className="mono">{r.doc_date}</td>
            <td>{r.recipient}</td><td className="mono">{r.gstin || '—'}</td>
            <td className="mono">{r.pos}</td>
            <td className="r mono">{inr(r.invoice_value)}</td><td className="r mono">{inr(r.taxable)}</td>
            <td className="r mono">{inr(r.igst)}</td><td className="r mono">{inr(r.cgst)}</td>
            <td className="r mono">{inr(r.sgst)}</td></tr>))}
      </Table>
    </div>) : null

  return (<>
    {flash}
    <Panel title="GSTR-1 — as it would be filed" right={selector}>
      {section('b2b', 'b2b — registered recipients', g1.sections.b2b)}
      {section('b2cl', 'b2cl — inter-state, unregistered, above ₹2,50,000', g1.sections.b2cl)}
      {section('b2cs', 'b2cs — unregistered', g1.sections.b2cs)}
      <Alert kind="ok"><b>Period total:</b> taxable {money(g1.totals.taxable)}, IGST{' '}
        {money(g1.totals.igst)}, CGST {money(g1.totals.cgst)}, SGST {money(g1.totals.sgst)}.</Alert>
      {g1.cancelled.length > 0 && <Alert kind="warn">{g1.cancelled.length} cancelled invoice{g1.cancelled.length === 1 ? '' : 's'} excluded
        ({g1.cancelled.map(c => c.doc_no).join(', ')}) and reported in table 13.</Alert>}
      {g1.proforma_excluded > 0 && <Alert kind="warn">
        {g1.proforma_excluded} proforma invoice{g1.proforma_excluded === 1 ? '' : 's'} excluded.
        A proforma is not a tax document and carries no GST liability.</Alert>}
      <div className="ft">
        <button className="btn btn-sm btn-a" onClick={() => api.gstr1Portal(period, 'json').catch(x => showFlash(x.message, 'bad'))}>Portal JSON</button>
        <button className="btn btn-sm" onClick={() => api.gstr1Portal(period, 'xlsx').catch(x => showFlash(x.message, 'bad'))}>Offline tool Excel</button>
        {['b2b', 'b2cs', 'hsn', 'docs'].map(s =>
          <button key={s} className="btn btn-sm" onClick={() => api.gstr1SectionCsv(s, period).catch(x => showFlash(x.message, 'bad'))}>{s}.csv</button>)}
      </div>
      <Alert kind="warn"><b>Column sets differ between versions of the GST Returns Offline Tool.</b>
        Check yours against the headings before a live filing.</Alert>
    </Panel>

    <GstFiling period={period} />

    <Panel title="GSTR-3B summary" bodyless>
      <Table head={['Table', 'Particulars', { label: 'Taxable value', align: 'r' },
        { label: 'IGST', align: 'r' }, { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]}>
        <tr><td className="mono">3.1(a)</td>
          <td>Outward taxable supplies<div className="fine">{g3.outward.documents} invoices</div></td>
          <td className="r mono">{inr(g3.outward.taxable)}</td>
          <td className="r mono">{inr(g3.outward.igst)}</td>
          <td className="r mono">{inr(g3.outward.cgst)}</td>
          <td className="r mono">{inr(g3.outward.sgst)}</td></tr>
        <tr><td className="mono">4(A)(5)</td>
          <td>All other input tax credit<div className="fine">
            {g3.itc.documents} {g3.itc.source}</div></td>
          <td className="r mono">{inr(g3.itc.taxable)}</td>
          <td className="r mono">{inr(g3.itc.igst)}</td>
          <td className="r mono">{inr(g3.itc.cgst)}</td>
          <td className="r mono">{inr(g3.itc.sgst)}</td></tr>
        <tr style={{ background: 'var(--accent-soft)' }}>
          <td className="mono"><b>Net</b></td><td><b>Tax payable after input credit</b></td>
          <td className="r mono">—</td>
          <td className="r mono"><b>{inr(g3.net_payable.igst)}</b></td>
          <td className="r mono"><b>{inr(g3.net_payable.cgst)}</b></td>
          <td className="r mono"><b>{inr(g3.net_payable.sgst)}</b></td></tr>
      </Table>
      <div className="panel-bd"><Alert kind="warn"><b>Indicative only.</b> {g3.caveat}</Alert></div>
    </Panel>
  </>)
}
