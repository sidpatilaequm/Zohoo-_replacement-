import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { STOCK_TYPES, stockMeta, expiryFrom } from '../lib/stock'
import { gd, today } from '../lib/fmt'

export default function GoodsReceipt() {
  const { api } = useAuth()
  const pos = useLoad(() => api.openPos())
  const [h, setH] = useState({ po_id: '', doc_no: '', doc_date: today(), delivery_note: '' })
  const [lines, setLines] = useState([])
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()

  const po = (pos.data || []).find(p => p.id === Number(h.po_id))
  function loadPo(id) {
    setH({ ...h, po_id: id })
    const p = (pos.data || []).find(x => x.id === Number(id))
    setLines(p ? p.lines.map(l => ({ ...l, qty: l.open, stock_type: 'NORMAL',
      batch: '', mfg_date: '', exp_date: '' })) : [])
  }
  const set = (i, k, v) => setLines(lines.map((l, j) => {
    if (j !== i) return l
    const n = { ...l, [k]: v }
    if (k === 'mfg_date' && n.shelf_life_days) n.exp_date = expiryFrom(v, n.shelf_life_days)
    return n
  }))
  const problems = []
  if (!h.po_id) problems.push('Select a purchase order.')
  if (!h.doc_no.trim()) problems.push('Receipt number is required.')
  if (!lines.some(l => Number(l.qty) > 0)) problems.push('Enter a received quantity on at least one line.')
  lines.forEach((l, i) => {
    if (Number(l.qty) > l.open + 0.0001) problems.push(`Line ${i + 1}: only ${l.open} remain open.`)
    if (Number(l.qty) > 0 && l.batch_managed && !l.batch.trim())
      problems.push(`Line ${i + 1}: ${l.code} is batch managed, so a batch number is required.`)
  })
  const mismatch = lines.filter(l => Number(l.qty) > 0 && Math.abs(Number(l.qty) - l.ordered) > 0.0001)

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const r = await api.postGrn({ ...h, po_id: Number(h.po_id),
        lines: lines.filter(l => Number(l.qty) > 0).map(l => ({
          material_id: l.material_id, qty: Number(l.qty), stock_type: l.stock_type,
          batch: l.batch || null, mfg_date: l.mfg_date || null,
          exp_date: l.exp_date || null })) })
      showFlash(`Receipt ${r.doc_no} posted. ${r.note}`,
        r.discrepancies.length ? 'bad' : 'ok')
      setLines([]); setH({ po_id: '', doc_no: '', doc_date: today(), delivery_note: '' })
      pos.reload()
    } catch (x) { setErr(x.message) }
  }
  if (pos.loading) return <Loading />
  if (pos.error) return <ErrorBox>{pos.error}</ErrorBox>

  return (<form onSubmit={save}>
    {flash}
    <Panel title="Receive goods against a purchase order">
      <div className="row">
        <Field label="Purchase order" hint="Only orders with something still to deliver">
          <select value={h.po_id} onChange={e => loadPo(e.target.value)}>
            <option value="">— select —</option>
            {(pos.data || []).map(p => (
              <option key={p.id} value={p.id}>{p.doc_no} · {p.vendor}</option>))}
          </select></Field>
        <Field label="Receipt note number"><input className="mono" value={h.doc_no} required
          onChange={e => setH({ ...h, doc_no: e.target.value })} /></Field>
        <Field label="Receipt date"><input type="date" value={h.doc_date} required
          onChange={e => setH({ ...h, doc_date: e.target.value })} /></Field>
        <Field label="Vendor delivery note"><input className="mono" value={h.delivery_note}
          onChange={e => setH({ ...h, delivery_note: e.target.value })} /></Field>
      </div>
      {po && <Alert kind="ok"><b>{po.vendor}</b> · against {po.doc_no} dated {gd(po.doc_date)}<br />
        Deliver to {(po.ship_addr || '').split('\n')[0]}</Alert>}
    </Panel>

    <Panel title="Lines received" bodyless>
      <Table head={['Material', { label: 'Ordered', align: 'r' }, { label: 'Open', align: 'r' },
        { label: 'Received', align: 'r' }, 'Stock type', 'Batch', 'Manufactured', 'Expiry',
        { label: 'Status', align: 'c' }]} empty="Select a purchase order.">
        {lines.map((l, i) => {
          const needBatch = l.batch_managed && Number(l.qty) > 0 && !l.batch.trim()
          const auto = l.shelf_life_days > 0
          return (<tr key={i}>
            <td>{l.descr}<div className="fine mono">{l.code}
              {l.batch_managed && <Tag kind="warn"> batch</Tag>}
              {l.shelf_life_days > 0 && <Tag> {l.shelf_life_days} d shelf</Tag>}</div></td>
            <td className="r mono">{l.ordered}</td>
            <td className="r mono">{l.open}</td>
            <td className="r"><input className="qty" type="number" min="0" value={l.qty}
              onChange={e => set(i, 'qty', e.target.value)} /></td>
            <td><select value={l.stock_type} onChange={e => set(i, 'stock_type', e.target.value)}
              style={{ padding: '6px 8px', border: '1px solid var(--line2)',
                borderRadius: 6, width: 130 }}>
              {STOCK_TYPES.map(t => <option key={t.code} value={t.code}>{t.label}</option>)}
            </select></td>
            <td>{l.batch_managed
              ? <input className={'mono' + (needBatch ? ' err' : '')} value={l.batch}
                  placeholder="batch no" style={{ padding: '6px 8px',
                    border: '1px solid var(--line2)', borderRadius: 6, width: 110 }}
                  onChange={e => set(i, 'batch', e.target.value)} />
              : <span className="fine">not batch managed</span>}</td>
            <td>{l.batch_managed
              ? <input type="date" value={l.mfg_date} style={{ padding: '6px 8px',
                  border: '1px solid var(--line2)', borderRadius: 6 }}
                  onChange={e => set(i, 'mfg_date', e.target.value)} />
              : <span className="fine">—</span>}</td>
            <td>{l.batch_managed
              ? (<><input type="date" value={l.exp_date} readOnly={auto}
                  style={{ padding: '6px 8px', border: '1px solid var(--line2)',
                    borderRadius: 6, background: auto ? '#F2F5F3' : '#fff' }}
                  onChange={e => set(i, 'exp_date', e.target.value)} />
                  {auto && <div className="fine">auto from shelf life</div>}</>)
              : <span className="fine">—</span>}</td>
            <td className="c">{!Number(l.qty) ? <Tag>nothing</Tag>
              : needBatch ? <Tag kind="bad">batch needed</Tag>
              : stockMeta(l.stock_type).owned ? <Tag kind="ok">Owned</Tag>
              : <Tag kind="warn">Vendor owned</Tag>}</td>
          </tr>)})}
      </Table>
      {lines.length > 0 && <div className="panel-bd">
        {mismatch.length > 0 && <Alert kind="warn">
          <b>{mismatch.length} line{mismatch.length === 1 ? '' : 's'} will not match the order.</b>
          {mismatch.map(l => (<div key={l.code} style={{ marginTop: 5 }}>
            {l.code} — ordered {l.ordered}, delivering {Number(l.qty)}{' '}
            <b>({Number(l.qty) - l.ordered > 0 ? '+' : ''}{Number(l.qty) - l.ordered})</b></div>))}
          <div style={{ marginTop: 7 }}>Each is raised as a discrepancy and <b>held</b>. The vendor
            cannot invoice a held line until it is released under Stock Discrepancy.</div>
        </Alert>}
        <Alert kind="ok">Only owned stock raises the quantity available to invoice. Consignment sits
          on your premises but belongs to the vendor until consumed, so it is reported separately.</Alert>
      </div>}
    </Panel>

    <div className="ft">
      <button className="btn btn-a" disabled={problems.length > 0}>Post goods receipt</button>
      <span className="err">{err || problems[0] || ''}</span>
    </div>
  </form>)
}
