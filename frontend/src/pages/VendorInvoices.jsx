import { useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

export default function VendorInvoices() {
  const { api } = useAuth()
  const pos = useLoad(() => api.pos())
  const materials = useLoad(() => api.materials())
  const list = useLoad(() => api.vinvs())
  const [h, setH] = useState({ po_id: '', doc_no: '', doc_date: today(), due_date: '' })
  const [lines, setLines] = useState([])
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setH(s => ({ ...s, [k]: v }))

  const openPos = (pos.data || []).filter(o => o.status === 'OPEN')
  const po = openPos.find(o => o.id === Number(h.po_id))

  function loadPo(id) {
    set('po_id', id)
    const o = openPos.find(x => x.id === Number(id))
    setLines(o ? o.lines.map(l => ({ material_id: l.material_id, poQty: l.qty,
      poPrice: l.price, qty: l.qty, price: l.price })) : [])
  }
  const calc = useMemo(() => {
    let taxable = 0, tax = 0
    const rows = lines.map(l => {
      const m = materials.data?.find(x => x.id === l.material_id)
      if (!m) return null
      const amount = Math.round(Number(l.qty) * Number(l.price) * 100) / 100
      const registered = po && po.tax > 0
      const t = registered ? Math.round(amount * m.igst_pct) / 100 : 0
      taxable += amount; tax += t
      return { ...l, m, amount, tax: t }
    }).filter(Boolean)
    return { rows, taxable, tax, rounded: Math.round(taxable + tax) }
  }, [lines, materials.data, po])

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const d = await api.addVinv({ doc_no: h.doc_no, doc_date: h.doc_date,
        due_date: h.due_date || null, po_id: Number(h.po_id),
        lines: lines.map(l => ({ material_id: l.material_id, qty: Number(l.qty),
          price: Number(l.price) })) })
      const v = d.variance
      showFlash(`Vendor invoice ${d.doc_no} recorded — ${money(d.totals.rounded)}.`
        + (v && Math.abs(v.difference) > 0.005
          ? ` Variance against the purchase order: ₹${inr(v.difference)}.` : ' It matches the purchase order.'))
      setLines([]); setH({ po_id: '', doc_no: '', doc_date: today(), due_date: '' })
      pos.reload(); list.reload()
    } catch (x) { setErr(x.message) }
  }
  if (pos.loading || materials.loading || list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <form onSubmit={save}>
      <Panel title="Record vendor invoice against a purchase order">
        <div className="row">
          <Field label="Purchase order" hint="Lines and prices are pulled from the order">
            <select value={h.po_id} onChange={e => loadPo(e.target.value)}>
              <option value="">— select —</option>
              {openPos.map(o => <option key={o.id} value={o.id}>{o.doc_no} · {o.vendor}</option>)}
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
      </Panel>

      {lines.length > 0 && <Panel title="Lines" bodyless>
        <Table head={['#', 'Material', { label: 'PO qty', align: 'r' },
          { label: 'Invoiced qty', align: 'r' }, { label: 'PO price', align: 'r' },
          { label: 'Invoiced price', align: 'r' }, { label: 'Amount', align: 'r' },
          { label: 'Variance', align: 'c' }]}>
          {calc.rows.map((r, i) => {
            const qv = Number(r.qty) - r.poQty, pv = Number(r.price) - r.poPrice
            const flag = Math.abs(qv) > 0.001 || Math.abs(pv) > 0.001
            return (<tr key={i}>
              <td className="mono">{i + 1}</td>
              <td>{r.m.descr}<div className="fine mono">{r.m.code}</div></td>
              <td className="r mono">{r.poQty}</td>
              <td className="r"><input className="qty" type="number" min="0" value={r.qty}
                onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, qty: e.target.value } : l))} /></td>
              <td className="r mono">{inr(r.poPrice)}</td>
              <td className="r"><input className="pr" type="number" min="0" step="0.01" value={r.price}
                onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, price: e.target.value } : l))} /></td>
              <td className="r mono"><b>{inr(r.amount)}</b></td>
              <td className="c">{flag
                ? <Tag kind="warn">{qv ? `${qv > 0 ? '+' : ''}${qv} qty ` : ''}
                    {pv ? `${pv > 0 ? '+' : ''}${inr(pv)} price` : ''}</Tag>
                : <Tag kind="ok">Matches</Tag>}</td>
            </tr>)})}
        </Table>
        <div className="panel-bd"><div className="totals">
          <div className="tr"><span>Taxable value</span><span>{inr(calc.taxable)}</span></div>
          <div className="tr grand"><span>Invoice value</span><span>{money(calc.rounded)}</span></div>
        </div></div>
      </Panel>}

      <div className="ft">
        <button className="btn btn-a" disabled={!h.po_id || !h.doc_no || !lines.length}>
          Record vendor invoice</button>
        <span className="err">{err}</span>
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
