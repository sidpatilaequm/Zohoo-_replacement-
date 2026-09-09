import { useMemo, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

const Conf = ({ v, how }) => v >= 0.9 ? <Tag kind="ok">{how || 'matched'}</Tag>
  : v >= 0.6 ? <Tag kind="warn">check · {how}</Tag> : <Tag kind="bad">not matched</Tag>

export default function VendorInvoices() {
  const { api } = useAuth()
  const pos = useLoad(() => api.pos())
  const vendors = useLoad(() => api.vendors())
  const materials = useLoad(() => api.materials())
  const caps = useLoad(() => api.extractCaps())
  const list = useLoad(() => api.vinvs())
  const [h, setH] = useState({ po_id: '', vendor_id: '', doc_no: '', doc_date: today(), due_date: '' })
  const [lines, setLines] = useState([])
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const [reading, setReading] = useState(false)
  const [prop, setProp] = useState(null)   // last extraction proposal
  const fileRef = useRef(null)
  const set = (k, v) => setH(s => ({ ...s, [k]: v }))

  const openPos = (pos.data || []).filter(o => o.status === 'OPEN')
  const po = openPos.find(o => o.id === Number(h.po_id))
  const vendor = (vendors.data || []).find(v => v.id === Number(po ? po.vendor_id : h.vendor_id))

  function loadPo(id) {
    set('po_id', id)
    const o = openPos.find(x => x.id === Number(id))
    if (o) set('vendor_id', String(o.vendor_id))
    setLines(o ? o.lines.map(l => ({ material_id: l.material_id, poQty: l.qty,
      poPrice: l.price, qty: l.qty, price: l.price })) : [])
  }

  /** Upload the vendor's PDF/image, read it, and fill the form from the proposal. */
  async function readFile(file) {
    if (!file) return
    setReading(true); setErr(null); setProp(null)
    try {
      const d = await api.extractVinv(file)
      setProp(d)
      const o = d.po_id ? openPos.find(x => x.id === d.po_id) : null
      const poLines = o ? Object.fromEntries(o.lines.map(l => [l.material_id, l])) : {}
      setH({ po_id: o ? String(o.id) : '', vendor_id: d.vendor_id ? String(d.vendor_id) : '',
        doc_no: d.doc_no || '', doc_date: d.doc_date || today(), due_date: d.due_date || '' })
      setLines(d.lines.map(l => ({ material_id: l.material_id, qty: l.qty, price: l.price,
        poQty: poLines[l.material_id]?.qty, poPrice: poLines[l.material_id]?.price,
        read: l })))
      showFlash(`Read ${file.name} (${d.read_method}${d.llm_used ? ' + model' : ''}) — `
        + `${d.lines.length} line(s). Check the highlighted fields, then record.`)
    } catch (x) { setErr(x.message) }
    finally { setReading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const registered = po ? po.tax > 0 : !!(vendor?.gstins || []).length
  const calc = useMemo(() => {
    let taxable = 0, tax = 0
    const rows = lines.map(l => {
      const m = materials.data?.find(x => x.id === l.material_id)
      const amount = Math.round(Number(l.qty) * Number(l.price) * 100) / 100
      const t = registered && m ? Math.round(amount * m.igst_pct) / 100 : 0
      taxable += amount; tax += t
      return { ...l, m, amount, tax: t }
    })
    return { rows, taxable, tax, rounded: Math.round(taxable + tax) }
  }, [lines, materials.data, registered])

  const unmatched = lines.filter(l => !l.material_id).length
  const canSave = !!h.doc_no && lines.length > 0 && unmatched === 0 && (h.po_id || h.vendor_id)

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const d = await api.addVinv({ doc_no: h.doc_no, doc_date: h.doc_date,
        due_date: h.due_date || null, po_id: h.po_id ? Number(h.po_id) : null,
        vendor_id: h.po_id ? null : Number(h.vendor_id),
        lines: lines.map(l => ({ material_id: l.material_id, qty: Number(l.qty),
          price: Number(l.price) })) })
      const v = d.variance
      showFlash(`Vendor invoice ${d.doc_no} recorded — ${money(d.totals.rounded)}.`
        + (v ? (Math.abs(v.difference) > 0.005
          ? ` Variance against the purchase order: ₹${inr(v.difference)}.` : ' It matches the purchase order.') : ''))
      setLines([]); setProp(null)
      setH({ po_id: '', vendor_id: '', doc_no: '', doc_date: today(), due_date: '' })
      pos.reload(); list.reload()
    } catch (x) { setErr(x.message) }
  }
  if (pos.loading || vendors.loading || materials.loading || list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <Panel title="Upload the vendor's invoice — PDF or image" right={
      caps.data && <span className="fine">
        PDF text {caps.data.pdf_text ? '✓' : '✗'} · OCR {caps.data.ocr ? '✓' : '✗ (tesseract not installed)'}
        · Model {caps.data.llm ? '✓' : '✗ (set ANTHROPIC_API_KEY)'}</span>}>
      <div className="ft" style={{ marginTop: 0 }}>
        <input type="file" ref={fileRef} accept=".pdf,image/*" disabled={reading}
          onChange={e => readFile(e.target.files?.[0])}
          style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7, maxWidth: 360 }} />
        <span className="fine">{reading ? 'Reading the invoice…'
          : 'The invoice number, dates, vendor (by GSTIN), purchase order and line items are read and filled in below. Nothing is saved until you press Record.'}</span>
      </div>
      {prop && <>
        <div className="row" style={{ marginTop: 12 }}>
          <Field label="Vendor read from file">
            <div>{prop.vendor_name || '—'} <Conf v={prop.vendor_confidence} how="GSTIN / name" />
              {prop.vendor_gstin && <div className="fine mono">{prop.vendor_gstin}</div>}</div></Field>
          <Field label="PO read from file"><div className="mono">{prop.po_no || '—'}{' '}
            {prop.po_no && (prop.po_id ? <Tag kind="ok">found</Tag> : <Tag kind="warn">not found</Tag>)}</div></Field>
          <Field label="Taxable / total printed"><div className="mono">
            {prop.taxable != null ? inr(prop.taxable) : '—'} / {prop.total != null ? inr(prop.total) : '—'}</div></Field>
        </div>
        {prop.warnings.length > 0 && <Alert kind="warn">
          <b>Check before recording:</b><ul style={{ margin: '4px 0 0 18px' }}>
            {prop.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></Alert>}
        <details style={{ marginTop: 8 }}><summary className="fine" style={{ cursor: 'pointer' }}>
          Text read from the file</summary>
          <pre className="fine" style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto',
            background: 'var(--paper)', padding: 10, borderRadius: 7 }}>{prop.text_preview}</pre></details>
      </>}
    </Panel>

    <form onSubmit={save}>
      <Panel title="Record vendor invoice">
        <div className="row">
          <Field label="Purchase order" hint="Optional — lines and prices are pulled from the order">
            <select value={h.po_id} onChange={e => loadPo(e.target.value)}>
              <option value="">— none / direct invoice —</option>
              {openPos.map(o => <option key={o.id} value={o.id}>{o.doc_no} · {o.vendor}</option>)}
            </select></Field>
          <Field label="Vendor" hint={po ? 'Taken from the purchase order' : 'Required when there is no PO'}>
            <select value={po ? String(po.vendor_id) : h.vendor_id} disabled={!!po}
              onChange={e => set('vendor_id', e.target.value)}>
              <option value="">— select —</option>
              {vendors.data.map(v => <option key={v.id} value={v.id}>{v.code} · {v.name}</option>)}
            </select></Field>
          <Field label="Vendor invoice number"><input className="mono" value={h.doc_no}
            onChange={e => set('doc_no', e.target.value)} required /></Field>
          <Field label="Invoice date"><input type="date" value={h.doc_date}
            onChange={e => set('doc_date', e.target.value)} required /></Field>
          <Field label="Due date"><input type="date" value={h.due_date}
            onChange={e => set('due_date', e.target.value)} /></Field>
        </div>
        {po && <Alert kind="ok"><b>{po.vendor}</b> · against {po.doc_no} dated {gd(po.doc_date)}<br />
          Deliver to {(po.ship_addr || '').split('\n')[0]}</Alert>}
        {!po && vendor && <Alert kind={registered ? 'ok' : 'warn'}><b>{vendor.name}</b> ·{' '}
          {registered ? 'registered vendor, input credit applies' : 'unregistered — no GST, no input credit'}</Alert>}
      </Panel>

      {lines.length > 0 && <Panel title="Lines" bodyless>
        <Table head={['#', 'Material', 'Read from file', { label: 'PO qty', align: 'r' },
          { label: 'Invoiced qty', align: 'r' }, { label: 'PO price', align: 'r' },
          { label: 'Invoiced price', align: 'r' }, { label: 'Amount', align: 'r' },
          { label: 'Variance', align: 'c' }, '']}>
          {calc.rows.map((r, i) => {
            const qv = r.poQty != null ? Number(r.qty) - r.poQty : 0
            const pv = r.poPrice != null ? Number(r.price) - r.poPrice : 0
            const flag = Math.abs(qv) > 0.001 || Math.abs(pv) > 0.001
            return (<tr key={i} style={!r.material_id ? { background: 'var(--red-soft)' } : undefined}>
              <td className="mono">{i + 1}</td>
              <td><select value={r.material_id || ''} style={{ minWidth: 220, padding: '6px 8px',
                  border: '1px solid var(--line2)', borderRadius: 7 }}
                onChange={e => setLines(lines.map((l, j) => j === i
                  ? { ...l, material_id: Number(e.target.value) || null } : l))}>
                <option value="">— pick a material —</option>
                {materials.data.map(m => <option key={m.id} value={m.id}>{m.code} · {m.descr}</option>)}
              </select></td>
              <td className="fine">{r.read ? <>{r.read.descr}
                {r.read.hsn && <span className="mono"> · {r.read.hsn}</span>}<br />
                <Conf v={r.read.confidence} how={r.read.matched_by} /></> : '—'}</td>
              <td className="r mono">{r.poQty ?? '—'}</td>
              <td className="r"><input className="qty" type="number" min="0" step="any" value={r.qty}
                onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, qty: e.target.value } : l))} /></td>
              <td className="r mono">{r.poPrice != null ? inr(r.poPrice) : '—'}</td>
              <td className="r"><input className="pr" type="number" min="0" step="0.01" value={r.price}
                onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, price: e.target.value } : l))} /></td>
              <td className="r mono"><b>{inr(r.amount)}</b></td>
              <td className="c">{r.poQty == null ? <Tag>No PO</Tag> : flag
                ? <Tag kind="warn">{qv ? `${qv > 0 ? '+' : ''}${qv} qty ` : ''}
                    {pv ? `${pv > 0 ? '+' : ''}${inr(pv)} price` : ''}</Tag>
                : <Tag kind="ok">Matches</Tag>}</td>
              <td className="r"><button type="button" className="rm"
                onClick={() => setLines(lines.filter((_, j) => j !== i))}>×</button></td>
            </tr>)})}
        </Table>
        <div className="panel-bd"><div className="totals">
          <div className="tr"><span>Taxable value</span><span>{inr(calc.taxable)}</span></div>
          {registered && <div className="tr"><span>Input tax</span><span>{inr(calc.tax)}</span></div>}
          <div className="tr grand"><span>Invoice value</span><span>{money(calc.rounded)}</span></div>
          {prop?.total != null && Math.abs(prop.total - calc.rounded) > 1 &&
            <div className="tr" style={{ color: 'var(--amber)' }}><span>Printed total on the file</span>
              <span>{inr(prop.total)}</span></div>}
        </div></div>
      </Panel>}

      <div className="ft">
        <button className="btn btn-a" disabled={!canSave}>Record vendor invoice</button>
        <span className="err">{err || (unmatched ? `${unmatched} line(s) still need a material.` : '')}</span>
      </div>
    </form>

    <Panel title={`Vendor invoice register — ${list.data.length}`} bodyless>
      <Table head={['Invoice', 'Date', 'Vendor', 'Against PO', { label: 'Supply', align: 'c' },
        { label: 'Taxable', align: 'r' }, { label: 'Input tax', align: 'r' },
        { label: 'Total', align: 'r' }, { label: 'Paid', align: 'r' },
        { label: 'Status', align: 'c' }]} empty="No vendor invoices yet.">
        {list.data.map(v => (
          <tr key={v.id}>
            <td className="mono"><b>{v.doc_no}</b></td>
            <td className="mono">{gd(v.doc_date)}</td>
            <td>{v.vendor}</td>
            <td className="mono">{v.po_no || '—'}</td>
            <td className="c">{v.tax > 0
              ? (v.intra ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>)
              : <Tag>None</Tag>}</td>
            <td className="r mono">{inr(v.taxable)}</td>
            <td className="r mono">{inr(v.tax)}</td>
            <td className="r mono"><b>{inr(v.total)}</b></td>
            <td className="r mono">{inr(v.paid)}</td>
            <td className="c">{v.outstanding <= 0.5 ? <Tag kind="ok">Settled</Tag>
              : v.paid > 0.5 ? <Tag kind="warn">Part paid</Tag> : <Tag>Unpaid</Tag>}</td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
