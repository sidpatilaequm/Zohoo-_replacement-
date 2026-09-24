import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox } from '../components/ui'
import { inr, gd } from '../lib/fmt'

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const label = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }
const signed = v => (v > 0 ? '+' : '') + inr(v)

export default function Audit() {
  const { api } = useAuth()
  const periods = useLoad(() => api.periods())
  const [period, setPeriod] = useState('')
  // GSTR-1 and GSTR-3B are monthly, so the GST half of this only means
  // something against a period. Land on the most recent one.
  useEffect(() => {
    if (!period && periods.data && periods.data.length) setPeriod(periods.data[0])
  }, [periods.data, period])
  const p = period || null
  const rec = useLoad(() => api.auditReconcile(p), [p])
  const txns = useLoad(() => api.auditTxns(p), [p])
  const [view, setView] = useState('recon')

  if (periods.loading || rec.loading) return <Loading />
  if (rec.error) return <ErrorBox>{rec.error}</ErrorBox>
  const r = rec.data
  const gst = r.gst, tds = r.tds

  const controls = (
    <select value={period} onChange={e => setPeriod(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      <option value="">All periods — TDS only</option>
      {(periods.data || []).map(x => <option key={x} value={x}>{label(x)}</option>)}
    </select>)

  return (<>
    <Panel title="Audit" right={<>
      {controls}
      <select value={view} onChange={e => setView(e.target.value)}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
        <option value="recon">Reconciliation</option>
        <option value="txns">All transactions</option>
      </select></>}>
      <Alert kind="ok"><b>This screen is read only.</b> An auditor can open every document
        here and change none of them. The reconciliation below runs on its own against the
        records held here; it is not a filing and does not touch the portal.</Alert>
      {!period && <Alert kind="warn">GSTR-1 and GSTR-3B are monthly returns, so the GST
        comparison needs a period. Choose one above. The TDS check below runs across
        everything regardless.</Alert>}
      <Alert kind={r.clean ? 'ok' : 'bad'}>
        <b>{r.clean ? 'Nothing to look at.' : `${r.issue_count} item${
          r.issue_count === 1 ? '' : 's'} need looking at.`}</b> {r.note}</Alert>
    </Panel>

    {view === 'recon' && (<>
      <Panel title="GST — register against GSTR-1 against what was filed" bodyless>
        <Table head={['Head', { label: 'Invoice register', align: 'r' },
          { label: 'GSTR-1', align: 'r' }, { label: 'GSTR-3B filed', align: 'r' },
          { label: 'Register vs GSTR-1', align: 'r' },
          { label: 'GSTR-1 vs filed', align: 'r' }, { label: '', align: 'c' }]}>
          {gst.rows.map(x => (
            <tr key={x.head}>
              <td><b>{x.head}</b></td>
              <td className="r mono">{inr(x.register)}</td>
              <td className="r mono">{x.gstr1 === null ? '—' : inr(x.gstr1)}</td>
              <td className="r mono">{x.gstr3b_filed === null
                ? <span className="fine">not uploaded</span> : inr(x.gstr3b_filed)}</td>
              <td className="r mono" style={x.register_vs_gstr1 &&
                Math.abs(x.register_vs_gstr1) > 1 ? { color: 'var(--red)',
                  fontWeight: 600 } : {}}>
                {x.register_vs_gstr1 === null ? '—' : signed(x.register_vs_gstr1)}</td>
              <td className="r mono" style={x.gstr1_vs_filed &&
                Math.abs(x.gstr1_vs_filed) > 1 ? { color: 'var(--red)',
                  fontWeight: 600 } : {}}>
                {x.gstr1_vs_filed === null ? '—' : signed(x.gstr1_vs_filed)}</td>
              <td className="c">{x.agrees
                ? <Tag kind="ok">agrees</Tag> : <Tag kind="bad">differs</Tag>}</td>
            </tr>))}
        </Table>
        <div className="panel-bd">
          {gst.issues.length > 0
            ? <Alert kind="bad">{gst.issues.map((i, n) => <div key={n}>{i}</div>)}</Alert>
            : <Alert kind="ok">Every head agrees within a rupee.</Alert>}
          <div className="fine">
            {gst.excluded.proforma} proforma and {gst.excluded.cancelled} cancelled
            document{gst.excluded.cancelled === 1 ? '' : 's'} excluded. A proforma carries
            no liability and a cancelled invoice carries none either, so neither belongs in
            the comparison.
          </div>
        </div>
      </Panel>

      <Panel title={`TDS — deducted against the vendor master · ${inr(tds.total_deducted)} deducted`}
        bodyless>
        <Table head={['Payment date', 'Vendor', 'PAN', { label: 'Section', align: 'c' },
          { label: 'Master rate', align: 'r' }, 'Vendor invoice',
          { label: 'Taxable', align: 'r' }, { label: 'Expected', align: 'r' },
          { label: 'Deducted', align: 'r' }, { label: 'Difference', align: 'r' },
          'What to look at']}
          empty="No tax was deducted in this period.">
          {tds.rows.map((x, i) => (
            <tr key={i}>
              <td className="mono">{gd(x.pay_date)}</td>
              <td>{x.vendor}<div className="fine mono">{x.vendor_code}</div></td>
              <td className="mono">{x.pan
                || <span style={{ color: 'var(--red)' }}>missing</span>}</td>
              <td className="c mono">{x.section || '—'}</td>
              <td className="r mono">{x.master_rate_pct ? x.master_rate_pct + '%' : '—'}</td>
              <td className="mono">{x.vendor_invoice}
                <div className="fine">{gd(x.invoice_date)}</div></td>
              <td className="r mono">{inr(x.taxable)}</td>
              <td className="r mono">{inr(x.expected_tds)}</td>
              <td className="r mono"><b>{inr(x.actual_tds)}</b></td>
              <td className="r mono" style={Math.abs(x.difference) > 1
                ? { color: 'var(--red)', fontWeight: 600 } : {}}>
                {signed(x.difference)}</td>
              <td className="fine">{x.flags.length
                ? x.flags.map((f, n) => <div key={n}>{f}</div>)
                : <Tag kind="ok">agrees</Tag>}</td>
            </tr>))}
        </Table>
        <div className="panel-bd">
          <Alert kind={tds.clean ? 'ok' : 'bad'}>
            Deducted {inr(tds.total_deducted)} against {inr(tds.total_expected)} expected
            from the rates on the vendor master, a difference of {signed(tds.difference)}.
          </Alert>
          {tds.vendors_without_pan.length > 0 && <Alert kind="bad">
            <b>No PAN on file for {tds.vendors_without_pan.join(', ')}.</b> Section 206AA
            requires a higher rate where the deductee has not furnished a PAN, so a
            deduction at the ordinary rate is short by law and not only by arithmetic.
          </Alert>}
        </div>
      </Panel>
    </>)}

    {view === 'txns' && (
      <Panel title={`Every transaction — ${(txns.data || []).length}`} bodyless>
        <Table head={[{ label: 'Kind', align: 'c' }, 'Document', 'Date', 'Party', 'GSTIN',
          { label: 'Taxable', align: 'r' }, { label: 'Tax', align: 'r' },
          { label: 'Total', align: 'r' }, { label: 'Settled', align: 'r' },
          { label: 'Status', align: 'c' }]}
          empty="Nothing in this period.">
          {(txns.data || []).map((x, i) => (
            <tr key={i} style={x.status === 'CANCELLED' ? { opacity: .6 } : undefined}>
              <td className="c"><Tag kind={
                x.kind === 'Customer invoice' ? 'ok'
                  : x.kind === 'Vendor invoice' ? 'warn' : 'no'}>{x.kind}</Tag></td>
              <td className="mono"><b>{x.doc_no}</b>
                <div className="fine">{x.doc_type}</div></td>
              <td className="mono">{gd(x.doc_date)}</td>
              <td>{x.party}</td>
              <td className="mono">{x.gstin || '—'}</td>
              <td className="r mono">{x.taxable === null ? '—' : inr(x.taxable)}</td>
              <td className="r mono">{inr(x.tax)}</td>
              <td className="r mono"><b>{inr(x.total)}</b></td>
              <td className="r mono">{x.settled === null ? '—' : inr(x.settled)}</td>
              <td className="c">{x.status === 'CANCELLED'
                ? <Tag kind="bad">Cancelled</Tag> : <Tag kind="ok">Active</Tag>}</td>
            </tr>))}
        </Table>
      </Panel>)}
  </>)
}
