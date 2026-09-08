import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { stockMeta } from '../lib/stock'
import { gd, today } from '../lib/fmt'

export default function PhysicalInventory() {
  const { api } = useAuth()
  const sheet = useLoad(() => api.countSheet())
  const history = useLoad(() => api.counts())
  const [counts, setCounts] = useState({})
  const [h, setH] = useState({ doc_no: '', count_date: today(), counted_by: '', reason: '' })
  const [scope, setScope] = useState('ALL')
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()

  if (sheet.loading) return <Loading />
  if (sheet.error) return <ErrorBox>{sheet.error}</ErrorBox>

  const key = r => `${r.material_id}|${r.batch}|${r.stock_type}`
  let rows = sheet.data
  if (scope === 'BATCH') rows = rows.filter(r => r.batch)
  if (scope === 'DIFF') rows = rows.filter(r => {
    const v = counts[key(r)]
    return v !== undefined && v !== '' && Number(v) !== r.book_qty
  })
  const pending = sheet.data.map(r => {
    const v = counts[key(r)]
    if (v === undefined || v === '') return null
    const d = Number(v) - r.book_qty
    return d === 0 ? null : { ...r, counted: Number(v), diff: d }
  }).filter(Boolean)
  const up = pending.filter(p => p.diff > 0).reduce((a, b) => a + b.diff, 0)
  const dn = pending.filter(p => p.diff < 0).reduce((a, b) => a + b.diff, 0)

  async function post(e) {
    e.preventDefault(); setErr(null)
    try {
      const r = await api.postCount({ ...h,
        lines: pending.map(p => ({ material_id: p.material_id, batch: p.batch || null,
          stock_type: p.stock_type, counted_qty: p.counted })) })
      showFlash(`Count ${r.doc_no} posted — ${r.posted.length} adjustment(s).`)
      setCounts({}); setH({ ...h, doc_no: '' })
      sheet.reload(); history.reload()
    } catch (x) { setErr(x.message) }
  }

  return (<>
    {flash}
    <Alert kind="ok"><b>Count what is actually on the shelf, then post the difference.</b> Book
      quantity is what the system believes; enter the counted quantity beside it. Posting writes an
      adjustment against that exact material, batch and stock type, so the stock report and the
      material quantity move together and the reason stays on record.</Alert>

    <form onSubmit={post}>
      <Panel title={`Count sheet — ${rows.length} lines`} right={<>
        <select value={scope} onChange={e => setScope(e.target.value)}
          style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
          <option value="ALL">Everything with stock</option>
          <option value="BATCH">Batch managed only</option>
          <option value="DIFF">Only lines with a difference</option>
        </select>
        <button type="button" className="btn btn-sm" onClick={() => {
          const n = {}; sheet.data.forEach(r => { n[key(r)] = String(r.book_qty) })
          setCounts(n)
        }}>Fill counted with book</button></>} bodyless>
        <Table head={['Material', 'Batch', 'Expiry', { label: 'Stock type', align: 'c' },
          { label: 'Book', align: 'r' }, { label: 'Counted', align: 'r' },
          { label: 'Difference', align: 'r' }, { label: 'Effect', align: 'c' }]}
          empty="No stock to count. Receive goods first.">
          {rows.map(r => {
            const k = key(r), raw = counts[k]
            const counted = raw === undefined || raw === '' ? null : Number(raw)
            const diff = counted === null ? null : counted - r.book_qty
            return (<tr key={k}>
              <td>{r.code}<div className="fine">{r.descr}</div></td>
              <td className="mono">{r.batch || '—'}</td>
              <td className="mono">{r.exp_date ? gd(r.exp_date) : '—'}</td>
              <td className="c"><Tag kind={stockMeta(r.stock_type).kind}>
                {stockMeta(r.stock_type).label}</Tag></td>
              <td className="r mono">{r.book_qty}</td>
              <td className="r"><input className="qty" type="number" min="0" placeholder="—"
                value={raw === undefined ? '' : raw}
                onChange={e => setCounts({ ...counts, [k]: e.target.value })} /></td>
              <td className="r mono" style={diff ? { fontWeight: 600,
                color: diff < 0 ? 'var(--red)' : 'var(--accent)' } : {}}>
                {diff === null ? '—' : (diff > 0 ? '+' : '') + diff}</td>
              <td className="c">{diff === null ? <Tag>not counted</Tag>
                : diff === 0 ? <Tag kind="ok">agrees</Tag>
                : diff < 0 ? <Tag kind="bad">write down</Tag> : <Tag kind="warn">write up</Tag>}</td>
            </tr>)})}
        </Table>
        <div className="panel-bd">
          <div className="row">
            <Field label="Count document number"><input className="mono" value={h.doc_no} required
              onChange={e => setH({ ...h, doc_no: e.target.value })} /></Field>
            <Field label="Count date"><input type="date" value={h.count_date} required
              onChange={e => setH({ ...h, count_date: e.target.value })} /></Field>
            <Field label="Counted by"><input value={h.counted_by}
              onChange={e => setH({ ...h, counted_by: e.target.value })} /></Field>
            <Field label="Reason or reference"><input value={h.reason}
              placeholder="cycle count, year end, damage found"
              onChange={e => setH({ ...h, reason: e.target.value })} /></Field>
          </div>
          {pending.length
            ? <Alert kind="warn"><b>{pending.length} line{pending.length === 1 ? '' : 's'} differ
                from the book.</b>{up ? ` ${up} units to write up.` : ''}
                {dn ? ` ${Math.abs(dn)} units to write down.` : ''} Posting adjusts the ledger and
                the material quantity together. Only owned stock types change the sellable figure.</Alert>
            : <Alert kind="ok">Nothing counted differs from the book, so there is nothing to post.</Alert>}
          <div className="ft">
            <button className="btn btn-a" disabled={!pending.length || !h.doc_no.trim()}>
              Post differences</button>
            <button type="button" className="btn" onClick={() => setCounts({})}>Clear counts</button>
            <span className="err">{err}</span></div>
        </div>
      </Panel>
    </form>

    <Panel title={`Posted counts — ${(history.data || []).length}`} bodyless>
      <Table head={['Document', 'Date', 'Counted by', 'Material', 'Batch',
        { label: 'Stock type', align: 'c' }, { label: 'Book', align: 'r' },
        { label: 'Counted', align: 'r' }, { label: 'Posted difference', align: 'r' }, 'Reason']}
        empty="Nothing posted yet.">
        {(history.data || []).map((p, i) => (
          <tr key={i}>
            <td className="mono"><b>{p.doc_no}</b></td><td className="mono">{gd(p.count_date)}</td>
            <td>{p.counted_by || '—'}</td>
            <td>{p.material}<div className="fine">{p.descr}</div></td>
            <td className="mono">{p.batch || '—'}</td>
            <td className="c"><Tag kind={stockMeta(p.stock_type).kind}>
              {stockMeta(p.stock_type).label}</Tag></td>
            <td className="r mono">{p.book}</td><td className="r mono">{p.counted}</td>
            <td className="r mono" style={{ fontWeight: 600,
              color: p.difference < 0 ? 'var(--red)' : 'var(--accent)' }}>
              {p.difference > 0 ? '+' : ''}{p.difference}</td>
            <td className="fine">{p.reason || '—'}</td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
