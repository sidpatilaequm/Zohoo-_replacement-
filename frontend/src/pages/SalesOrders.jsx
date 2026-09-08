import { useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

export default function SalesOrders() {
  const { api } = useAuth()
  const customers = useLoad(() => api.customers())
  const materials = useLoad(() => api.materials())
  const list = useLoad(() => api.salesOrders())
  const stock = useLoad(() => api.stockSummary())
  const [h, setH] = useState({ doc_no: '', doc_date: today(), req_date: '',
    customer_id: '', cust_ref: '' })
  const [lines, setLines] = useState([])
  const [pick, setPick] = useState('')
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()

  const avail = useMemo(() => Object.fromEntries(
    (stock.data || []).map(s => [s.material_id, s.normal || 0])), [stock.data])

  const calc = useMemo(() => {
    let total = 0
    const rows = lines.map(l => {
      const m = materials.data?.find(x => x.id === l.material_id)
      if (!m) return null
      const amt = Math.round(Number(l.qty) * Number(l.price) * 100) / 100
      total += amt
      return { ...l, m, amt, avail: avail[m.id] || 0 }
    }).filter(Boolean)
    return { rows, total }
  }, [lines, materials.data, avail])

  const problems = []
  if (!h.customer_id) problems.push('Select a customer.')
  if (!lines.length) problems.push('Add at least one line.')
  lines.forEach((l, i) => {
    if (Number(l.qty) <= 0) problems.push(`Line ${i + 1}: quantity must be more than zero.`)
    if (Number(l.price) <= 0) problems.push(`Line ${i + 1}: price must be more than zero.`)
  })

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const r = await api.addSalesOrder({ ...h, doc_no: h.doc_no || null,
        req_date: h.req_date || null, customer_id: Number(h.customer_id),
        lines: lines.map(l => ({ material_id: l.material_id, qty: Number(l.qty),
          price: Number(l.price) })) })
      showFlash(`Order ${r.doc_no} saved. ${r.note}`, r.short.length ? 'bad' : 'ok')
      setLines([]); setH({ ...h, doc_no: '', customer_id: '', cust_ref: '' })
      list.reload()
    } catch (x) { setErr(x.message) }
  }
  if (customers.loading || materials.loading || list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>
  const cust = customers.data.find(c => c.id === Number(h.customer_id))

  return (<>
    {flash}
    <form onSubmit={save}>
      <Panel title="Create sales order">
        <div className="row">
          <Field label="Customer"><select value={h.customer_id} required
            onChange={e => setH({ ...h, customer_id: e.target.value })}>
            <option value="">— select —</option>
            {customers.data.map(c => (
              <option key={c.id} value={c.id}>{c.code} · {c.name}</option>))}
          </select></Field>
          <Field label="Order number" hint="Left blank, one is allocated">
            <input className="mono" value={h.doc_no}
              onChange={e => setH({ ...h, doc_no: e.target.value })} /></Field>
          <Field label="Order date"><input type="date" value={h.doc_date} required
            onChange={e => setH({ ...h, doc_date: e.target.value })} /></Field>
          <Field label="Required by"><input type="date" value={h.req_date}
            onChange={e => setH({ ...h, req_date: e.target.value })} /></Field>
          <Field label="Customer reference"><input className="mono" value={h.cust_ref}
            placeholder="their PO number"
            onChange={e => setH({ ...h, cust_ref: e.target.value })} /></Field>
        </div>
        {cust && <Alert kind="ok"><b>{cust.name}</b><br />
          Ship to {cust.ship_same
            ? `${cust.bill_addr}, ${cust.bill_city}`
            : `${cust.ship_addr}, ${cust.ship_city}`}</Alert>}
      </Panel>

      <Panel title="Order lines" right={<>
        <select value={pick} onChange={e => setPick(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--line2)',
            borderRadius: 7, minWidth: 250 }}>
          <option value="">— select a material —</option>
          {materials.data.map(m => <option key={m.id} value={m.id}>{m.code} · {m.descr}</option>)}
        </select>
        <button type="button" className="btn btn-sm btn-a" onClick={() => {
          const m = materials.data.find(x => x.id === Number(pick))
          if (m) setLines([...lines, { material_id: m.id, qty: 1, price: m.price }])
        }}>Add line</button></>} bodyless>
        <Table head={['#', 'Material', { label: 'Quantity', align: 'r' },
          { label: 'UoM', align: 'c' }, { label: 'Available', align: 'r' },
          { label: 'Unit price', align: 'r' }, { label: 'Amount', align: 'r' },
          { label: 'Cover', align: 'c' }, '']} empty="No lines yet.">
          {calc.rows.map((r, i) => {
            const short = Number(r.qty) > r.avail + 0.0001
            return (<tr key={i}>
              <td className="mono">{i + 1}</td>
              <td>{r.m.descr}<div className="fine mono">{r.m.code}</div></td>
              <td className="r"><input className="qty" type="number" min="0" value={r.qty}
                onChange={e => setLines(lines.map((l, j) =>
                  j === i ? { ...l, qty: e.target.value } : l))} /></td>
              <td className="c mono">{r.m.uom}</td>
              <td className="r mono">{r.avail}</td>
              <td className="r"><input className="pr" type="number" min="0" step="0.01"
                value={r.price} onChange={e => setLines(lines.map((l, j) =>
                  j === i ? { ...l, price: e.target.value } : l))} /></td>
              <td className="r mono"><b>{inr(r.amt)}</b></td>
              <td className="c">{short
                ? <Tag kind="warn">short by {(Number(r.qty) - r.avail).toFixed(0)}</Tag>
                : <Tag kind="ok">covered</Tag>}</td>
              <td className="r"><button type="button" className="rm"
                onClick={() => setLines(lines.filter((_, j) => j !== i))}>×</button></td>
            </tr>)})}
        </Table>
        {lines.length > 0 && <div className="panel-bd">
          <div className="totals"><div className="tr grand">
            <span>Order value</span><span>{money(calc.total)}</span></div></div>
          {calc.rows.some(r => Number(r.qty) > r.avail + 0.0001) && <Alert kind="warn">
            <b>Some lines exceed what is on hand.</b> The order can still be taken — it simply
            cannot be delivered in full until stock arrives. Delivery will only let you pick what
            actually exists.</Alert>}
        </div>}
      </Panel>

      <div className="ft">
        <button className="btn btn-a" disabled={problems.length > 0}>Save sales order</button>
        <button type="button" className="btn" onClick={() => setLines([])}>Clear</button>
        <span className="err">{err || problems[0] || ''}</span></div>
    </form>

    <Panel title={`Sales orders — ${list.data.length}`} bodyless>
      <Table head={['Order', 'Date', 'Customer', 'Reference', { label: 'Lines', align: 'r' },
        { label: 'Ordered', align: 'r' }, { label: 'Delivered', align: 'r' },
        { label: 'Value', align: 'r' }, { label: 'Status', align: 'c' }, '']}
        empty="No sales orders yet.">
        {list.data.map(o => {
          const ord = o.lines.reduce((a, b) => a + b.qty, 0)
          const del = o.lines.reduce((a, b) => a + b.delivered, 0)
          return (<tr key={o.id}>
            <td className="mono"><b>{o.doc_no}</b></td><td className="mono">{gd(o.doc_date)}</td>
            <td>{o.customer}</td><td className="mono">{o.cust_ref || '—'}</td>
            <td className="r mono">{o.lines.length}</td>
            <td className="r mono">{ord}</td><td className="r mono">{del}</td>
            <td className="r mono">{inr(o.value)}</td>
            <td className="c">{o.status === 'DELIVERED' ? <Tag kind="ok">Delivered</Tag>
              : o.status === 'PARTIAL' ? <Tag kind="warn">Part delivered</Tag>
              : <Tag>Open</Tag>}</td>
            <td className="r">{o.status === 'OPEN' && <button className="rm" onClick={async () => {
              try { await api.delSalesOrder(o.id); list.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>×</button>}</td>
          </tr>)})}
      </Table>
    </Panel>
  </>)
}
