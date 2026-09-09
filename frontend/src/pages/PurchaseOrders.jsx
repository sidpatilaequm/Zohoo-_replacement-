import { useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

export default function PurchaseOrders() {
  const { api, me } = useAuth()
  const vendors = useLoad(() => api.vendors())
  const materials = useLoad(() => api.materials())
  const list = useLoad(() => api.pos())
  const t = me?.tenant
  const orgAddr = t ? `${t.name}\nGSTIN ${t.gstin || '—'}` : ''
  const [h, setH] = useState({ vendor_id: '', gstin: '', doc_date: today(), req_date: '',
    bill_addr: '', ship_same: true, ship_addr: '' })
  const [lines, setLines] = useState([])
  const [pick, setPick] = useState('')
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const [variant, setVariant] = usePrintVariant()
  const set = (k, v) => setH(s => ({ ...s, [k]: v }))

  const vend = vendors.data?.find(v => v.id === Number(h.vendor_id))
  const regs = vend?.gstins || []
  const reg = regs.find(r => r.gstin === h.gstin) || regs.find(r => r.is_default) || regs[0]
  const registered = !!reg
  const intra = (reg?.state_code || vend?.state_code) === t?.state_code

  const calc = useMemo(() => {
    let taxable = 0, cgst = 0, sgst = 0, igst = 0
    const rows = lines.map(l => {
      const m = materials.data?.find(x => x.id === l.material_id)
      if (!m) return null
      const amount = Math.round(Number(l.qty) * Number(l.price) * 100) / 100
      const c = registered && intra ? Math.round(amount * m.cgst_pct) / 100 : 0
      const s = registered && intra ? Math.round(amount * m.sgst_pct) / 100 : 0
      const i = registered && !intra ? Math.round(amount * m.igst_pct) / 100 : 0
      taxable += amount; cgst += c; sgst += s; igst += i
      return { ...l, m, amount, c, s, i, rate: registered ? (intra ? m.cgst_pct + m.sgst_pct : m.igst_pct) : 0 }
    }).filter(Boolean)
    const total = taxable + cgst + sgst + igst
    return { rows, taxable, cgst, sgst, igst, rounded: Math.round(total),
      roundoff: Math.round(total) - total }
  }, [lines, materials.data, intra, registered])

  const problems = []
  if (!h.vendor_id) problems.push('Select a vendor.')
  if (!lines.length) problems.push('Add at least one line.')
  if (!h.ship_same && !h.ship_addr.trim()) problems.push('Enter the delivery address.')
  lines.forEach((l, i) => {
    if (Number(l.qty) <= 0) problems.push(`Line ${i + 1}: quantity must be more than zero.`)
    if (Number(l.price) <= 0) problems.push(`Line ${i + 1}: cost price must be more than zero.`)
  })

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const d = await api.addPo({ ...h, vendor_id: Number(h.vendor_id),
        gstin: reg?.gstin || null, req_date: h.req_date || null,
        bill_addr: h.bill_addr || orgAddr,
        ship_addr: h.ship_same ? null : h.ship_addr,
        lines: lines.map(l => ({ material_id: l.material_id, qty: Number(l.qty),
          price: Number(l.price) })) })
      showFlash(`Purchase order ${d.doc_no} saved — ${money(d.totals.rounded)}.`)
      setLines([]); setH(s => ({ ...s, vendor_id: '', gstin: '' })); list.reload()
    } catch (x) { setErr(x.message) }
  }
  if (vendors.loading || materials.loading || list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <form onSubmit={save}>
      <Panel title="Raise purchase order">
        <div className="row">
          <Field label="Vendor"><select value={h.vendor_id}
            onChange={e => { set('vendor_id', e.target.value); set('gstin', '') }}>
            <option value="">— select —</option>
            {vendors.data.map(v => <option key={v.id} value={v.id}>{v.code} · {v.name}</option>)}
          </select></Field>
          <Field label="Vendor GST registration">
            <select value={reg?.gstin || ''} disabled={regs.length < 2}
              onChange={e => set('gstin', e.target.value)}>
              {regs.length ? regs.map(r => <option key={r.id} value={r.gstin}>{r.gstin}</option>)
                : <option value="">Unregistered — no input credit</option>}
            </select></Field>
          <Field label="PO date"><input type="date" value={h.doc_date}
            onChange={e => set('doc_date', e.target.value)} required /></Field>
          <Field label="Required by"><input type="date" value={h.req_date}
            onChange={e => set('req_date', e.target.value)} /></Field>
        </div>
        <div className="grid2" style={{ marginTop: 16 }}>
          <Field label="Billing address — invoice to be raised on"
            hint="Left blank, the organisation address is used">
            <textarea value={h.bill_addr} placeholder={orgAddr}
              onChange={e => set('bill_addr', e.target.value)} /></Field>
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 7,
              cursor: 'pointer', fontSize: 12.5 }}>
              <input type="checkbox" checked={h.ship_same} style={{ width: 16, height: 16 }}
                onChange={e => set('ship_same', e.target.checked)} />
              Delivery address same as billing</label>
            <Field label="Delivery address — where goods are sent">
              <textarea value={h.ship_same ? (h.bill_addr || orgAddr) : h.ship_addr}
                disabled={h.ship_same}
                onChange={e => set('ship_addr', e.target.value)} /></Field>
          </div>
        </div>
        {vend && <Alert kind={registered ? 'ok' : 'warn'}>
          {registered
            ? <><b>{intra ? 'Intra-state' : 'Inter-state'} purchase.</b> Input tax credit of{' '}
                ₹{inr(calc.cgst + calc.sgst + calc.igst)} will carry to GSTR-3B table 4.</>
            : <><b>Unregistered vendor.</b> No GST is charged and there is no input tax credit.</>}
        </Alert>}
      </Panel>

      <Panel title="Order lines" right={<>
        <select value={pick} onChange={e => setPick(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7, minWidth: 250 }}>
          <option value="">— select a material —</option>
          {materials.data.map(m => <option key={m.id} value={m.id}>{m.code} · {m.descr}</option>)}
        </select>
        <button type="button" className="btn btn-sm btn-a" onClick={() => {
          const m = materials.data.find(x => x.id === Number(pick))
          if (m) setLines([...lines, { material_id: m.id, qty: 1, price: m.cost || m.price }])
        }}>Add line</button></>} bodyless>
        <Table head={['#', 'Material', 'HSN', { label: 'Quantity', align: 'r' },
          { label: 'UoM', align: 'c' }, { label: 'Cost price', align: 'r' },
          { label: 'Amount', align: 'r' }, { label: 'Tax', align: 'r' }, '']} empty="No lines yet.">
          {calc.rows.map((r, i) => (
            <tr key={i}>
              <td className="mono">{i + 1}</td>
              <td>{r.m.descr}<div className="fine mono">{r.m.code}</div></td>
              <td className="mono">{r.m.hsn}</td>
              <td className="r"><input className="qty" type="number" min="0" value={r.qty}
                onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, qty: e.target.value } : l))} /></td>
              <td className="c mono">{r.m.uom}</td>
              <td className="r"><input className="pr" type="number" min="0" step="0.01" value={r.price}
                onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, price: e.target.value } : l))} />
                {r.m.cost > 0 && Math.abs(Number(r.price) - r.m.cost) > 0.001 &&
                  <div className="fine" style={{ color: 'var(--amber)' }}>cost {inr(r.m.cost)}</div>}</td>
              <td className="r mono"><b>{inr(r.amount)}</b></td>
              <td className="r mono">{inr(r.c + r.s + r.i)}</td>
              <td className="r"><button type="button" className="rm"
                onClick={() => setLines(lines.filter((_, j) => j !== i))}>×</button></td>
            </tr>))}
        </Table>
        {lines.length > 0 && <div className="panel-bd"><div className="totals">
          <div className="tr"><span>Taxable value</span><span>{inr(calc.taxable)}</span></div>
          {registered ? (intra ? (<>
            <div className="tr"><span>CGST input</span><span>{inr(calc.cgst)}</span></div>
            <div className="tr"><span>SGST input</span><span>{inr(calc.sgst)}</span></div></>)
            : <div className="tr"><span>IGST input</span><span>{inr(calc.igst)}</span></div>)
            : <div className="tr"><span>GST</span><span>nil — unregistered</span></div>}
          <div className="tr grand"><span>Order value</span><span>{money(calc.rounded)}</span></div>
        </div></div>}
      </Panel>

      <div className="ft">
        <button className="btn btn-a" disabled={problems.length > 0}>Save purchase order</button>
        <span className="err">{err || problems[0] || ''}</span>
      </div>
    </form>

    <Panel title={`Saved purchase orders — ${list.data.length}`}
      right={<VariantPicker value={variant} onChange={setVariant} />} bodyless>
      <Table head={['PO', 'Date', 'Vendor', 'Delivery', { label: 'Status', align: 'c' },
        { label: 'Supply', align: 'c' }, { label: 'Taxable', align: 'r' },
        { label: 'Input tax', align: 'r' }, { label: 'Total', align: 'r' },
        { label: 'Print', align: 'c' }]}
        empty="No purchase orders yet.">
        {list.data.map(o => (
          <tr key={o.id}>
            <td className="mono"><b>{o.doc_no}</b></td>
            <td className="mono">{gd(o.doc_date)}</td>
            <td>{o.vendor}</td>
            <td className="fine">{(o.ship_addr || '').split('\n')[0]}</td>
            <td className="c">{o.status === 'INVOICED'
              ? <Tag kind="ok">Invoiced</Tag> : <Tag kind="warn">Open</Tag>}</td>
            <td className="c">{o.tax > 0
              ? (o.intra ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>)
              : <Tag>None</Tag>}</td>
            <td className="r mono">{inr(o.taxable)}</td>
            <td className="r mono">{inr(o.tax)}</td>
            <td className="r mono"><b>{inr(o.total)}</b></td>
            <td className="c"><PrintButtons kind="purchase-orders" id={o.id} variant={variant}
              onError={m => showFlash(m, 'bad')} /></td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
