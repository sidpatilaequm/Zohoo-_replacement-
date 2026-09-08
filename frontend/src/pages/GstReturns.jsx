import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money } from '../lib/fmt'

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const label = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }

const B3_FIELDS = [
  ['out_taxable', 'Outward taxable value'], ['out_igst', 'Outward IGST'],
  ['out_cgst', 'Outward CGST'], ['out_sgst', 'Outward SGST'],
  ['itc_igst', 'Input credit IGST'], ['itc_cgst', 'Input credit CGST'],
  ['itc_sgst', 'Input credit SGST'],
]

export default function GstReturns() {
  const { api } = useAuth()
  const [b3, setB3] = useState(Object.fromEntries(B3_FIELDS.map(([k]) => [k, ''])))
  const [cmp, setCmp] = useState(null)
  const [b3err, setB3err] = useState(null)
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
    Promise.all([api.gstr1(period), api.gstr3b(period), api.recon(period)])
      .then(([g1, g3, rc]) => { if (alive) setData({ g1, g3, rc }) })
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

  async function loadCompare(p) {
    try { setCmp(await api.compare3b(p)) } catch (x) { setB3err(x.message) }
  }
  async function saveB3() {
    setB3err(null)
    try {
      const body = { period }
      B3_FIELDS.forEach(([k]) => { body[k] = Number(b3[k] || 0) })
      const r = await api.upload3b(body)
      setCmp(r)
      showFlash(r.all_agree
        ? 'Filed figures agree with the books.'
        : 'Saved. Some heads differ — see the comparison.', r.all_agree ? 'ok' : 'bad')
    } catch (x) { setB3err(x.message) }
  }
  function fillFromBooks() {
    if (!cmp || !cmp.book) return
    setB3(Object.fromEntries(B3_FIELDS.map(([k]) => [k, String(cmp.book[k] ?? 0)])))
  }
  if (err) return <><Panel title="GST returns" right={selector} /><ErrorBox>{err}</ErrorBox></>
  if (!data) return <><Panel title="GST returns" right={selector} /><Loading /></>

  const { g1, g3, rc } = data
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
      {g1.proforma_excluded > 0 && <Alert kind="warn">
        {g1.proforma_excluded} proforma invoice{g1.proforma_excluded === 1 ? '' : 's'} excluded.
        A proforma is not a tax document and carries no GST liability.</Alert>}
      <div className="ft">
        {['b2b', 'b2cs', 'hsn', 'docs'].map(s =>
          <a key={s} className="btn btn-sm" href={api.csvUrl(s, period)}>Download {s}.csv</a>)}
      </div>
      <Alert kind="warn"><b>Column sets differ between versions of the GST Returns Offline Tool.</b>
        Check yours against the headings before a live filing.</Alert>
    </Panel>

    <Panel title="GSTR-1 to GSTR-3B reconciliation" bodyless>
      <Table head={['Head', { label: 'GSTR-1', align: 'r' }, { label: 'GSTR-3B 3.1(a)', align: 'r' },
        { label: 'Difference', align: 'r' }, { label: 'Status', align: 'c' }]}>
        {rc.rows.map(r => (
          <tr key={r.head}>
            <td style={{ textTransform: 'capitalize' }}>{r.head}</td>
            <td className="r mono">{inr(r.gstr1)}</td><td className="r mono">{inr(r.gstr3b)}</td>
            <td className="r mono" style={r.agrees ? {} : { color: 'var(--red)', fontWeight: 600 }}>
              {inr(r.difference)}</td>
            <td className="c">{r.agrees ? <Tag kind="ok">Agrees</Tag> : <Tag kind="bad">Differs</Tag>}</td>
          </tr>))}
      </Table>
      <div className="panel-bd"><Alert kind={rc.all_agree ? 'ok' : 'bad'}>{rc.note}</Alert></div>
    </Panel>

    <Panel title="GSTR-3B as filed — upload and compare" right={<>
      <a className="btn btn-sm" href={api.template3bUrl()}>Download blank CSV</a>
      <button className="btn btn-sm" onClick={() => loadCompare(period)}>Load saved</button></>}>
      <p className="fine" style={{ margin: '0 0 10px' }}>
        Enter what was actually filed on the portal for {label(period)}. It is stored against the
        period and compared with the books head by head, which is what makes a reconciliation
        possible. Differences within one rupee are treated as rounding.</p>
      <div className="row">
        {B3_FIELDS.map(([k, lbl]) => (
          <Field key={k} label={lbl}>
            <input className="mono" type="number" step="0.01" value={b3[k]}
              placeholder="0.00" onChange={e => setB3({ ...b3, [k]: e.target.value })} />
          </Field>))}
      </div>
      <div className="ft">
        <button className="btn btn-a" onClick={saveB3}>Save and compare</button>
        <button className="btn" onClick={fillFromBooks} disabled={!cmp}>
          Copy the book figures in</button>
        {b3err && <span className="err">{b3err}</span>}
      </div>
      {cmp && cmp.filed && (<>
        <Table head={['Head', { label: 'Filed in GSTR-3B', align: 'r' },
          { label: 'Per the books', align: 'r' }, { label: 'Difference', align: 'r' },
          { label: 'Status', align: 'c' }]}>
          {cmp.rows.map(r => (
            <tr key={r.field}>
              <td>{r.head}</td>
              <td className="r mono">{inr(r.filed)}</td>
              <td className="r mono">{inr(r.book)}</td>
              <td className="r mono" style={r.agrees ? {}
                : { color: 'var(--red)', fontWeight: 600 }}>{inr(r.difference)}</td>
              <td className="c">{r.agrees
                ? <Tag kind="ok">Agrees</Tag> : <Tag kind="bad">Differs</Tag>}</td>
            </tr>))}
        </Table>
        <Alert kind={cmp.all_agree ? 'ok' : 'bad'}>
          {cmp.all_agree
            ? 'Every head agrees with the books.'
            : 'Some heads differ. '}{cmp.note}</Alert>
      </>)}
      {cmp && !cmp.filed && <Alert kind="warn">{cmp.note}</Alert>}
    </Panel>

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
