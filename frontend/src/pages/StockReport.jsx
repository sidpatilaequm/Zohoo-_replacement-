import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox } from '../components/ui'
import { STOCK_TYPES, stockMeta } from '../lib/stock'
import { gd } from '../lib/fmt'

const n = v => Number(v || 0).toLocaleString('en-IN')

export default function StockReport() {
  const { api } = useAuth()
  const [view, setView] = useState('summary')
  const sum = useLoad(() => api.stockSummary())
  const bat = useLoad(() => api.stockBatches())
  const mov = useLoad(() => api.stockMoves())
  if (sum.loading || bat.loading || mov.loading) return <Loading />
  const anyErr = sum.error || bat.error || mov.error
  if (anyErr) return <ErrorBox>{anyErr}</ErrorBox>

  const totals = Object.fromEntries(STOCK_TYPES.map(t =>
    [t.code, (sum.data || []).reduce((a, r) => a + (r[t.code.toLowerCase()] || 0), 0)]))
  const owned = (sum.data || []).reduce((a, r) => a + r.owned, 0)
  const inQ = (sum.data || []).reduce((a, r) => a + r.received, 0)
  const outQ = (sum.data || []).reduce((a, r) => a + r.issued, 0)
  const expired = (bat.data || []).filter(b => b.days_left !== null && b.days_left < 0)
    .reduce((a, b) => a + b.qty, 0)
  const soon = (bat.data || []).filter(b => b.days_left !== null && b.days_left >= 0 && b.days_left <= 90)
    .reduce((a, b) => a + b.qty, 0)

  function download() {
    const rows = [['Date', 'Document', 'Movement', 'Reference', 'Material', 'Description',
      'Batch', 'Stock type', 'Party', 'In', 'Out', 'Balance']]
    ;(mov.data || []).forEach(m => rows.push([gd(m.move_date), m.doc_no, m.movement,
      m.reference || '', m.code, m.descr, m.batch || '', stockMeta(m.stock_type).label,
      m.party || '', m.in_qty || '', m.out_qty || '', m.balance]))
    const csv = rows.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'stock_report.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (<>
    <Panel title="Stock report" right={<>
      <select value={view} onChange={e => setView(e.target.value)}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="summary">Summary by material and stock type</option>
        <option value="batch">Batch detail</option>
        <option value="expiry">Expiry watch</option>
        <option value="moves">Movements in and out</option>
      </select>
      <button className="btn btn-sm" onClick={download}>Export CSV</button></>}>
      <div className="row">
        {STOCK_TYPES.map(t => (
          <div key={t.code} style={{ border: '1px solid var(--line)', borderRadius: 9,
            padding: '12px 14px', background: '#fff' }}>
            <div className="fine" style={{ textTransform: 'uppercase', letterSpacing: '.08em' }}>
              {t.label}</div>
            <div style={{ fontSize: 20, fontWeight: 600, margin: '3px 0' }}>{n(totals[t.code])}</div>
            <div className="fine">{t.note}</div>
          </div>))}
      </div>
      <Alert kind={expired ? 'bad' : soon ? 'warn' : 'ok'}>
        <b>{n(owned)} units owned</b> and available to value.
        {expired ? <b> {n(expired)} units have passed expiry.</b> : null}
        {soon ? ` ${n(soon)} units expire within 90 days.` : null}
        {!expired && !soon ? ' Nothing is expired or expiring within 90 days.' : null}
        {' '}Consignment is excluded from the owned figure because it belongs to the vendor
        until consumed.
        <div style={{ marginTop: 6 }}>Movement to date: <b>{n(inQ)} in</b>, <b>{n(outQ)} out</b>,
          leaving {n(inQ - outQ)} on hand across every stock type.</div>
      </Alert>
    </Panel>

    <Panel bodyless>
      {view === 'summary' && (
        <Table head={['Material', 'Description', { label: 'UoM', align: 'c' },
          { label: 'Batch', align: 'c' }, { label: 'Received', align: 'r' },
          { label: 'Issued', align: 'r' },
          ...STOCK_TYPES.map(t => ({ label: t.label, align: 'r' })),
          { label: 'On hand', align: 'r' }]} empty="No stock yet.">
          {(sum.data || []).map(r => (
            <tr key={r.material_id}>
              <td className="mono"><b>{r.code}</b></td><td>{r.descr}</td>
              <td className="c mono">{r.uom}</td>
              <td className="c">{r.batch_managed ? <Tag kind="warn">Yes</Tag> : <Tag>No</Tag>}</td>
              <td className="r mono" style={{ color: 'var(--accent)' }}>
                {r.received ? '+' + n(r.received) : '—'}</td>
              <td className="r mono" style={{ color: 'var(--red)' }}>
                {r.issued ? '-' + n(r.issued) : '—'}</td>
              {STOCK_TYPES.map(t => (
                <td key={t.code} className="r mono">
                  {r[t.code.toLowerCase()] ? n(r[t.code.toLowerCase()]) : '—'}</td>))}
              <td className="r mono"><b>{n(r.owned)}</b></td>
            </tr>))}
        </Table>)}

      {view === 'batch' && (
        <Table head={['Material', 'Batch', 'Expiry', { label: 'Days left', align: 'c' },
          { label: 'Stock type', align: 'c' }, { label: 'Owned', align: 'c' },
          { label: 'Quantity', align: 'r' }]} empty="No stock yet.">
          {(bat.data || []).map((b, i) => (
            <tr key={i}>
              <td>{b.code}<div className="fine">{b.descr}</div></td>
              <td className="mono">{b.batch || '—'}</td>
              <td className="mono">{b.exp_date ? gd(b.exp_date) : '—'}</td>
              <td className="c">{b.days_left === null ? '—'
                : b.days_left < 0 ? <Tag kind="bad">expired {-b.days_left} d</Tag>
                : b.days_left <= 90 ? <Tag kind="warn">{b.days_left} d</Tag>
                : <Tag kind="ok">{b.days_left} d</Tag>}</td>
              <td className="c"><Tag kind={stockMeta(b.stock_type).kind}>
                {stockMeta(b.stock_type).label}</Tag></td>
              <td className="c">{b.owned ? 'Yes' : 'No'}</td>
              <td className="r mono"><b>{n(b.qty)}</b></td>
            </tr>))}
        </Table>)}

      {view === 'expiry' && (
        (bat.data || []).some(b => b.exp_date)
          ? <Table head={['Expiry', { label: 'Days left', align: 'c' }, 'Material', 'Batch',
              { label: 'Stock type', align: 'c' }, { label: 'Quantity', align: 'r' }]}>
              {(bat.data || []).filter(b => b.exp_date).map((b, i) => (
                <tr key={i} style={b.days_left < 0 ? { background: 'var(--red-soft)' }
                  : b.days_left <= 90 ? { background: 'var(--amber-soft)' } : {}}>
                  <td className="mono"><b>{gd(b.exp_date)}</b></td>
                  <td className="c">{b.days_left < 0
                    ? <Tag kind="bad">expired {-b.days_left} d ago</Tag>
                    : b.days_left <= 90 ? <Tag kind="warn">{b.days_left} d</Tag>
                    : <Tag kind="ok">{b.days_left} d</Tag>}</td>
                  <td>{b.code}<div className="fine">{b.descr}</div></td>
                  <td className="mono">{b.batch || '—'}</td>
                  <td className="c"><Tag kind={stockMeta(b.stock_type).kind}>
                    {stockMeta(b.stock_type).label}</Tag></td>
                  <td className="r mono"><b>{n(b.qty)}</b></td>
                </tr>))}
            </Table>
          : <div className="panel-bd"><Alert kind="ok">No batch has an expiry date recorded, so
              there is nothing to watch. Expiry appears once a batch-managed material is received
              with a manufacturing date.</Alert></div>)}

      {view === 'moves' && (
        <Table head={['Date', 'Document', { label: 'Movement', align: 'c' }, 'Material', 'Batch',
          { label: 'Stock type', align: 'c' }, 'Party', { label: 'In', align: 'r' },
          { label: 'Out', align: 'r' }, { label: 'Running balance', align: 'r' }]}
          empty="No movements yet. Receipts, issues and count adjustments all appear here.">
          {(mov.data || []).map((m, i) => (
            <tr key={i}>
              <td className="mono">{gd(m.move_date)}</td>
              <td className="mono">{m.doc_no}
                {m.reference && <div className="fine">{m.reference}</div>}</td>
              <td className="c"><Tag kind={m.source === 'GRN' ? 'ok'
                : m.source === 'GI' ? 'warn' : 'no'}>{m.movement}</Tag></td>
              <td>{m.code}<div className="fine">{m.descr}</div></td>
              <td className="mono">{m.batch || '—'}</td>
              <td className="c"><Tag kind={stockMeta(m.stock_type).kind}>
                {stockMeta(m.stock_type).label}</Tag></td>
              <td className="fine">{m.party || '—'}</td>
              <td className="r mono" style={{ color: 'var(--accent)' }}>
                {m.in_qty ? '+' + n(m.in_qty) : ''}</td>
              <td className="r mono" style={{ color: 'var(--red)' }}>
                {m.out_qty ? '-' + n(m.out_qty) : ''}</td>
              <td className="r mono"><b>{n(m.balance)}</b></td>
            </tr>))}
        </Table>)}
    </Panel>
  </>)
}
