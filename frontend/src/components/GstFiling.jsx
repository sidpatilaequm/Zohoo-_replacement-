import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from './ui'
import { inr, money } from '../lib/fmt'

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
export const periodLabel = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }

const B3_FIELDS = [
  ['out_taxable', 'Outward taxable value'], ['out_igst', 'Outward IGST'],
  ['out_cgst', 'Outward CGST'], ['out_sgst', 'Outward SGST'],
  ['itc_igst', 'Input credit IGST'], ['itc_cgst', 'Input credit CGST'],
  ['itc_sgst', 'Input credit SGST'],
]

/**
 * A — GSTR-1 built from the books, downloadable in the portal's JSON and the
 *     Returns Offline Tool workbook.
 * B — GSTR-3B as filed, uploaded here (portal JSON, CSV or typed in).
 * A − B — head by head.
 */
export default function GstFiling({ period: fixedPeriod }) {
  const { api } = useAuth()
  const periods = useLoad(() => api.periods())
  const [period, setPeriod] = useState(fixedPeriod || '')
  const [g1, setG1] = useState(null)
  const [ab, setAb] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [b3, setB3] = useState(Object.fromEntries(B3_FIELDS.map(([k]) => [k, ''])))
  const [flash, showFlash] = useFlash()
  const jsonRef = useRef(null), csvRef = useRef(null)

  useEffect(() => { if (fixedPeriod) setPeriod(fixedPeriod) }, [fixedPeriod])
  useEffect(() => {
    if (!period && !fixedPeriod && periods.data?.length) setPeriod(periods.data[0])
  }, [periods.data, period, fixedPeriod])

  async function load(p) {
    if (!p) return
    setErr(null)
    try {
      const [a, r] = await Promise.all([api.gstr1(p), api.reconAB(p)])
      setG1(a); setAb(r)
      // seed the 3B form with the uploaded figures, else the book figures
      const cmp = await api.compare3b(p)
      const src = cmp.filed || cmp.book
      setB3(Object.fromEntries(B3_FIELDS.map(([k]) => [k, src && src[k] != null ? String(src[k]) : ''])))
    } catch (x) { setErr(x.message) }
  }
  useEffect(() => { load(period) }, [period])   // eslint-disable-line react-hooks/exhaustive-deps

  async function dl(fn, label) {
    setBusy(true)
    try { await fn(); showFlash(`${label} downloaded.`) }
    catch (x) { showFlash(x.message, 'bad') }
    finally { setBusy(false) }
  }
  async function saveTyped() {
    try {
      const body = { period }
      B3_FIELDS.forEach(([k]) => { body[k] = Number(b3[k] || 0) })
      await api.upload3b(body)
      showFlash('GSTR-3B figures saved.'); load(period)
    } catch (x) { showFlash(x.message, 'bad') }
  }
  async function uploadFile(kind, file) {
    if (!file) return
    setBusy(true)
    try {
      const r = kind === 'json' ? await api.upload3bJson(period, file) : await api.upload3bCsv(period, file)
      showFlash(`GSTR-3B for ${periodLabel(period)} uploaded${r.read_from?.portal_period
        ? ` (portal period ${r.read_from.portal_period})` : ''}.`)
      load(period)
    } catch (x) { showFlash(x.message, 'bad') }
    finally { setBusy(false); if (jsonRef.current) jsonRef.current.value = ''; if (csvRef.current) csvRef.current.value = '' }
  }

  if (periods.loading) return <Loading />
  if (periods.error) return <ErrorBox>{periods.error}</ErrorBox>
  if (!periods.data?.length) return <Alert kind="warn">No documents saved yet, so there is nothing to file.</Alert>

  const selector = !fixedPeriod && (
    <select value={period} onChange={e => setPeriod(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      {periods.data.map(p => <option key={p} value={p}>{periodLabel(p)}</option>)}
    </select>)
  if (err) return <><Panel title="GST filing" right={selector} /><ErrorBox>{err}</ErrorBox></>
  if (!g1 || !ab) return <><Panel title="GST filing" right={selector} /><Loading /></>

  const rows = [...g1.sections.b2b.map(r => ({ ...r, sec: 'B2B' })),
                ...g1.sections.b2cl.map(r => ({ ...r, sec: 'B2CL' })),
                ...g1.sections.b2cs.map(r => ({ ...r, sec: 'B2CS' }))]

  return (<>
    {flash}
    <Panel title={`A — GSTR-1 register for ${periodLabel(period)} · ${rows.length} invoices`} right={<>
      {selector}
      <button className="btn btn-sm btn-a" disabled={busy}
        onClick={() => dl(() => api.gstr1Portal(period, 'json'), 'GSTR-1 JSON')}>Portal JSON</button>
      <button className="btn btn-sm" disabled={busy}
        onClick={() => dl(() => api.gstr1Portal(period, 'xlsx'), 'GSTR-1 workbook')}>Offline tool Excel</button>
      {['b2b', 'b2cs', 'hsn', 'docs'].map(s =>
        <button key={s} className="btn btn-sm" disabled={busy}
          onClick={() => dl(() => api.gstr1SectionCsv(s, period), `${s}.csv`)}>{s}.csv</button>)}
    </>} bodyless>
      <Table head={[{ label: 'Table', align: 'c' }, 'Invoice', 'Date', 'Recipient', 'GSTIN',
        'Place of supply', { label: 'Invoice value', align: 'r' }, { label: 'Taxable', align: 'r' },
        { label: 'IGST', align: 'r' }, { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]}
        empty="No tax invoices in this period.">
        {rows.map(r => (
          <tr key={r.doc_no}>
            <td className="c"><Tag kind={r.sec === 'B2B' ? 'ok' : 'warn'}>{r.sec}</Tag></td>
            <td className="mono"><b>{r.doc_no}</b></td><td className="mono">{r.doc_date}</td>
            <td>{r.recipient}</td><td className="mono">{r.gstin || '—'}</td>
            <td className="mono">{r.pos}</td>
            <td className="r mono">{inr(r.invoice_value)}</td><td className="r mono">{inr(r.taxable)}</td>
            <td className="r mono">{inr(r.igst)}</td><td className="r mono">{inr(r.cgst)}</td>
            <td className="r mono">{inr(r.sgst)}</td></tr>))}
        {rows.length > 0 && <tr style={{ background: 'var(--accent-soft)' }}>
          <td colSpan={7}><b>Total — goes to the portal as GSTR-1</b></td>
          <td className="r mono"><b>{inr(g1.totals.taxable)}</b></td>
          <td className="r mono"><b>{inr(g1.totals.igst)}</b></td>
          <td className="r mono"><b>{inr(g1.totals.cgst)}</b></td>
          <td className="r mono"><b>{inr(g1.totals.sgst)}</b></td></tr>}
      </Table>
      <div className="panel-bd">
        {g1.cancelled.length > 0 && <Alert kind="warn">
          <b>{g1.cancelled.length} cancelled invoice{g1.cancelled.length === 1 ? '' : 's'}</b> in this
          period ({g1.cancelled.map(c => c.doc_no).join(', ')}) — excluded from the tables above, counted
          as cancelled in table 13 (documents issued).</Alert>}
        <Alert kind="ok"><b>Portal JSON</b> is the GSTR-1 upload format (b2b, b2cl, b2cs, hsn, doc_issue) —
          import it in the Returns Offline Tool or upload on the portal. <b>Offline tool Excel</b> has one
          sheet per table with the tool's headings. Check the column set against your tool version before a
          live filing.</Alert>
      </div>
    </Panel>

    <Panel title={`B — GSTR-3B as filed for ${periodLabel(period)} · upload here`} right={
      <button className="btn btn-sm" onClick={() => dl(() => { window.location.href = api.template3bUrl(); return Promise.resolve() }, 'Template')}>
        Blank CSV</button>}>
      <div className="ft" style={{ marginTop: 0, flexWrap: 'wrap' }}>
        <Field label="Portal GSTR-3B JSON">
          <input type="file" accept=".json,application/json" ref={jsonRef} disabled={busy}
            onChange={e => uploadFile('json', e.target.files?.[0])} /></Field>
        <Field label="Or field,value CSV">
          <input type="file" accept=".csv,text/csv" ref={csvRef} disabled={busy}
            onChange={e => uploadFile('csv', e.target.files?.[0])} /></Field>
      </div>
      <p className="fine" style={{ margin: '8px 0 10px' }}>Or type what was filed. The form is pre-filled
        with the last upload, else the book figures. {ab.uploaded_by && <>Last upload by <b>{ab.uploaded_by}</b>.</>}</p>
      <div className="row">
        {B3_FIELDS.map(([k, lbl]) => (
          <Field key={k} label={lbl}>
            <input className="mono" type="number" step="0.01" value={b3[k]} placeholder="0.00"
              onChange={e => setB3({ ...b3, [k]: e.target.value })} /></Field>))}
      </div>
      <div className="ft"><button className="btn btn-a" onClick={saveTyped}>Save GSTR-3B figures</button></div>
    </Panel>

    <Panel title={`A − B — GSTR-1 against GSTR-3B for ${periodLabel(period)}`} bodyless>
      <Table head={['', 'Head', { label: 'A · GSTR-1 (books)', align: 'r' },
        { label: `B · GSTR-3B (${ab.b_source})`, align: 'r' }, { label: 'A − B', align: 'r' },
        { label: 'Status', align: 'c' }]}>
        {ab.rows.map(r => (
          <tr key={r.head}>
            <td className="fine">{r.section}</td><td>{r.head}</td>
            <td className="r mono">{inr(r.a)}</td><td className="r mono">{inr(r.b)}</td>
            <td className="r mono" style={r.agrees ? {} : { color: 'var(--red)', fontWeight: 600 }}>
              {inr(r.a_minus_b)}</td>
            <td className="c">{r.agrees ? <Tag kind="ok">Agrees</Tag> : <Tag kind="bad">Differs</Tag>}</td>
          </tr>))}
      </Table>
      <div className="panel-bd">
        <Alert kind={ab.b_source === 'books' ? 'warn' : ab.all_agree ? 'ok' : 'bad'}>
          {ab.b_source === 'books'
            ? <><b>No GSTR-3B uploaded for this period yet</b> — B is the 3B computed from the books, so A − B is nil by construction. Upload the filed return above to reconcile. </>
            : ab.all_agree ? <><b>Every head agrees.</b> </> : <><b>Some heads differ.</b> </>}
          {ab.note}</Alert>
      </div>
    </Panel>
  </>)
}
