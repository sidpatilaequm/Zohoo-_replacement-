import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { stockMeta } from '../lib/stock'
import { gd, today } from '../lib/fmt'

export default function Deliveries() {
  const { api } = useAuth()
  const orders = useLoad(() => api.salesOrders())
  const list = useLoad(() => api.deliveries())
  const [h, setH] = useState({ so_id: '', doc_no: '', doc_date: today(), ship_to: '' })
  const [plan, setPlan] = useState(null)
  const [picks, setPicks] = useState({})
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()

  const open = (orders.data || []).filter(o => o.status !== 'DELIVERED')

  useEffect(() => {
    if (!h.so_id) { setPlan(null); setPicks({}); return }
    let alive = true
    api.suggestPicks(Number(h.so_id)).then(p => {
      if (!alive) return
      setPlan(p)
      const init = {}
      p.lines.forEach(l => l.suggested.forEach(s => {
        init[`${l.material_id}|${s.batch}|${s.stock_type}`] = String(s.qty)
      }))
      setPicks(init)
    }).catch(e => setErr(e.message))
    return () => { alive = false }
  }, [h.so_id, api])

  if (orders.loading || list.loading) return <Loading />
  if (orders.error) return <ErrorBox>{orders.error}</ErrorBox>

  const pickList = Object.entries(picks)
    .map(([k, v]) => { const [mid, batch, st] = k.split('|')
      return { material_id: Number(mid), batch: batch || null, stock_type: st, qty: Number(v) } })
    .filter(p => p.qty > 0)
  const totalPicked = pickList.reduce((a, b) => a + b.qty, 0)

  async function post(e) {
    e.preventDefault(); setErr(null)
    try {
      const r = await api.postDelivery({ so_id: Number(h.so_id), doc_no: h.doc_no || null,
        doc_date: h.doc_date, ship_to: h.ship_to || null, picks: pickList })
      showFlash(`Delivery ${r.doc_no} posted, ${r.issued.length} line(s) issued. `
        + `The order is now ${r.order_status.toLowerCase()}.`)
      setH({ ...h, so_id: '', doc_no: '' }); setPlan(null); setPicks({})
      orders.reload(); list.reload()
    } catch (x) { setErr(x.message) }
  }

  return (<>
    {flash}
    <Alert kind="ok"><b>Pick from real batches, then post the goods issue.</b> A delivery is created
      from a sales order, stock is picked against specific batches and stock types, and posting
      takes it out of stock. Picking suggests the earliest expiry first, which you can override.</Alert>

    <form onSubmit={post}>
      <Panel title="Create delivery from a sales order">
        <div className="row">
          <Field label="Sales order" hint="Only orders with something still to deliver">
            <select value={h.so_id} onChange={e => setH({ ...h, so_id: e.target.value })}>
              <option value="">— select —</option>
              {open.map(o => <option key={o.id} value={o.id}>{o.doc_no} · {o.customer}</option>)}
            </select></Field>
          <Field label="Delivery number" hint="Left blank, one is allocated">
            <input className="mono" value={h.doc_no}
              onChange={e => setH({ ...h, doc_no: e.target.value })} /></Field>
          <Field label="Delivery date"><input type="date" value={h.doc_date} required
            onChange={e => setH({ ...h, doc_date: e.target.value })} /></Field>
          <Field label="Ship to"><input value={h.ship_to}
            onChange={e => setH({ ...h, ship_to: e.target.value })} /></Field>
        </div>
        {plan && <Alert kind="ok"><b>{plan.customer}</b> · against {plan.so_no}</Alert>}
      </Panel>

      <Panel title="Picking" right={plan && <button type="button" className="btn btn-sm"
        onClick={() => {
          const init = {}
          plan.lines.forEach(l => l.suggested.forEach(s => {
            init[`${l.material_id}|${s.batch}|${s.stock_type}`] = String(s.qty) }))
          setPicks(init)
        }}>Suggest picks by earliest expiry</button>} bodyless>
        <Table head={['Material', { label: 'Ordered', align: 'r' },
          { label: 'Already delivered', align: 'r' }, { label: 'Outstanding', align: 'r' },
          'Pick from', { label: 'Picked', align: 'r' }, { label: 'Status', align: 'c' }]}
          empty="Select a sales order.">
          {(plan?.lines || []).map(l => {
            const picked = l.available.reduce((a, av) =>
              a + Number(picks[`${l.material_id}|${av.batch}|${av.stock_type}`] || 0), 0)
            return (<tr key={l.material_id}>
              <td>{l.descr}<div className="fine mono">{l.code}
                {l.batch_managed && <Tag kind="warn"> batch</Tag>}</div></td>
              <td className="r mono">{l.ordered}</td>
              <td className="r mono">{l.delivered}</td>
              <td className="r mono"><b>{l.outstanding}</b></td>
              <td>{l.available.length ? l.available.map((av, j) => {
                const k = `${l.material_id}|${av.batch}|${av.stock_type}`
                return (<div key={j} style={{ display: 'flex', alignItems: 'center',
                  gap: 6, marginBottom: 3 }}>
                  <span className="mono" style={{ fontSize: 11, minWidth: 170 }}>
                    {av.batch || 'no batch'} · {stockMeta(av.stock_type).label}
                    {av.exp_date ? ` · exp ${gd(av.exp_date)}` : ''}{' '}
                    <span className="fine">({av.qty})</span></span>
                  <input className="qty" style={{ width: 74 }} type="number" min="0" max={av.qty}
                    value={picks[k] || 0}
                    onChange={e => setPicks({ ...picks, [k]: e.target.value })} />
                </div>)})
                : <span className="fine" style={{ color: 'var(--red)' }}>nothing on hand</span>}</td>
              <td className="r mono"><b>{picked}</b></td>
              <td className="c">{picked === 0 ? <Tag>nothing</Tag>
                : picked > l.outstanding ? <Tag kind="bad">over the order</Tag>
                : picked < l.outstanding ? <Tag kind="warn">short by {l.outstanding - picked}</Tag>
                : <Tag kind="ok">fully picked</Tag>}</td>
            </tr>)})}
        </Table>
        {plan && <div className="panel-bd"><Alert kind="ok">
          <b>{totalPicked} units picked.</b> Posting the goods issue removes them from stock against
          the exact batch and stock type picked, and the movement appears in the stock report as an
          issue.</Alert></div>}
      </Panel>

      <div className="ft">
        <button className="btn btn-a" disabled={!h.so_id || !pickList.length}>
          Post goods issue</button>
        <button type="button" className="btn" onClick={() => { setPicks({}) }}>Clear picks</button>
        <span className="err">{err}</span></div>
    </form>

    <Panel title={`Deliveries posted — ${list.data.length}`} bodyless>
      <Table head={['Delivery', 'Date', 'Against order', 'Customer', 'Material', 'Batch',
        'Expiry', { label: 'Stock type', align: 'c' }, { label: 'Issued', align: 'r' }]}
        empty="Nothing issued yet.">
        {list.data.map((d, i) => (
          <tr key={i}>
            <td className="mono"><b>{d.doc_no}</b></td><td className="mono">{gd(d.doc_date)}</td>
            <td className="mono">{d.so_no}</td><td>{d.customer}</td>
            <td>{d.code}<div className="fine">{d.descr}</div></td>
            <td className="mono">{d.batch || '—'}</td>
            <td className="mono">{d.exp_date ? gd(d.exp_date) : '—'}</td>
            <td className="c"><Tag kind={stockMeta(d.stock_type).kind}>
              {stockMeta(d.stock_type).label}</Tag></td>
            <td className="r mono"><b>{d.qty}</b></td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
