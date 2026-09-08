import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { gd } from '../lib/fmt'

export default function Discrepancies() {
  const { api } = useAuth()
  const [status, setStatus] = useState('HELD')
  const list = useLoad(() => api.discrepancies(status === 'ALL' ? null : status), [status])
  const inv = useLoad(() => api.discInvoiceable())
  const [flash, showFlash] = useFlash()

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  async function act(id, release) {
    try {
      const r = release ? await api.releaseDisc(id) : await api.holdDisc(id)
      if (release) showFlash(`Released. ${r.note}`)
      list.reload(); inv.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }

  return (<>
    {flash}
    <Alert kind="warn"><b>A discrepancy is held until someone releases it.</b> Where the quantity
      delivered differs from the quantity ordered, the line is parked here rather than passed
      straight through. <b>Until it is released, the vendor cannot invoice that line.</b> Once
      released, the <b>received</b> quantity becomes what they may invoice, not the ordered
      quantity. There is no approval workflow yet — anyone with access to this screen can release.</Alert>

    <Panel title="Discrepancies" right={
      <select value={status} onChange={e => setStatus(e.target.value)}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="HELD">Held — awaiting release</option>
        <option value="RELEASED">Released</option>
        <option value="ALL">All</option>
      </select>} bodyless>
      <Table head={['Receipt', 'Date', 'Against PO', 'Vendor', 'Material',
        { label: 'Ordered', align: 'r' }, { label: 'Delivered', align: 'r' },
        { label: 'Difference', align: 'r' }, { label: 'Type', align: 'c' },
        { label: 'Status', align: 'c' }, { label: 'Action', align: 'c' }]}
        empty="Nothing to show. A line appears here only when the delivered quantity differs from the ordered quantity.">
        {list.data.map(d => (
          <tr key={d.id}>
            <td className="mono"><b>{d.grn_no}</b></td>
            <td className="mono">{gd(d.grn_date)}</td>
            <td className="mono">{d.po_no}</td><td>{d.vendor}</td>
            <td>{d.material}<div className="fine">{d.descr}</div></td>
            <td className="r mono">{d.ordered}</td>
            <td className="r mono"><b>{d.received}</b></td>
            <td className="r mono" style={{ fontWeight: 600,
              color: d.difference < 0 ? 'var(--red)' : 'var(--amber)' }}>
              {d.difference > 0 ? '+' : ''}{d.difference}</td>
            <td className="c"><Tag kind={d.difference < 0 ? 'bad' : 'warn'}>{d.kind}</Tag></td>
            <td className="c">{d.status === 'HELD' ? <Tag kind="warn">Held</Tag>
              : <><Tag kind="ok">Released</Tag><div className="fine">{gd(d.released_on)}
                {d.released_by ? ` · ${d.released_by}` : ''}</div></>}</td>
            <td className="c">{d.status === 'HELD'
              ? <button className="btn btn-sm btn-a" onClick={() => act(d.id, true)}>Release</button>
              : <button className="btn btn-sm" onClick={() => act(d.id, false)}>Hold again</button>}</td>
          </tr>))}
      </Table>
    </Panel>

    <Panel title="Effect on what the vendor may invoice" bodyless>
      <Table head={['PO', 'Vendor', 'Material', { label: 'Ordered', align: 'r' },
        { label: 'Delivered', align: 'r' }, { label: 'Held', align: 'r' },
        { label: 'Invoiceable', align: 'r' }, { label: 'Position', align: 'c' }]}
        empty="Nothing received yet.">
        {(inv.data || []).map((r, i) => (
          <tr key={i}>
            <td className="mono">{r.po_no}</td><td>{r.vendor}</td>
            <td>{r.material}<div className="fine">{r.descr}</div></td>
            <td className="r mono">{r.ordered}</td>
            <td className="r mono">{r.delivered}</td>
            <td className="r mono" style={r.held ? { color: 'var(--red)' } : {}}>
              {r.held || '—'}</td>
            <td className="r mono"><b>{r.invoiceable}</b></td>
            <td className="c">{r.held ? <Tag kind="warn">Part held</Tag>
              : r.delivered === r.ordered ? <Tag kind="ok">Matches the order</Tag>
              : <Tag kind="ok">Released at delivered quantity</Tag>}</td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
