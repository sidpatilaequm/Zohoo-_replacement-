import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox } from './ui'
import { inr, money, gd } from '../lib/fmt'

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const monthLabel = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }

/** A strip of headline figures. */
function Figures({ items }) {
  return (<div className="sumstrip" style={{ marginTop: 0 }}>
    {items.map(([label, value, strong]) => <div key={label} className={strong ? 'net' : ''}>
      <span>{label}</span><b className="mono">{value}</b></div>)}
  </div>)
}

function TaxTable({ rows, first, firstKey, extra }) {
  return (<Table head={[first, ...(extra ? [extra.label] : []), { label: 'Taxable', align: 'r' }, { label: 'CGST', align: 'r' },
    { label: 'SGST', align: 'r' }, { label: 'IGST', align: 'r' }, { label: 'Total tax', align: 'r' }]} empty="Nothing in this period.">
    {rows.map(r => <tr key={r[firstKey]}>
      <td>{firstKey === 'month' ? monthLabel(r.month) : `${r.rate}%`}</td>
      {extra && <td className="r mono">{r[extra.key]}</td>}
      <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.cgst)}</td>
      <td className="r mono">{inr(r.sgst)}</td><td className="r mono">{inr(r.igst)}</td>
      <td className="r mono"><b>{inr(r.tax ?? (r.cgst + r.sgst + r.igst))}</b></td></tr>)}
  </Table>)
}

/* ============================================================ GST — sales */
export function GstSales({ period }) {
  const { api } = useAuth()
  const d = useLoad(() => api.gstSales(period), [period])
  if (d.loading) return <Loading />
  if (d.error) return <ErrorBox>{d.error}</ErrorBox>
  const D = d.data, T = D.totals
  return (<>
    <Panel title={`GST register — sales · ${D.rows.length} invoices`}>
      <Figures items={[['Taxable value', inr(T.taxable)], ['CGST', inr(T.cgst)], ['SGST', inr(T.sgst)], ['IGST', inr(T.igst)],
        ['Output GST', inr(T.tax), true], ['Invoice value', inr(T.total)]]} />
      <div className="fine" style={{ marginTop: 8 }}>B2B (registered customers): taxable {inr(D.b2b.taxable)}, GST {inr(D.b2b.tax)} ·
        B2C (unregistered): taxable {inr(D.b2c.taxable)}, GST {inr(D.b2c.tax)}. Tax invoices only; proformas are not supplies.</div>
    </Panel>
    <div className="grid2">
      <Panel title="By GST rate" bodyless><TaxTable rows={D.by_rate} first="Rate" firstKey="rate" /></Panel>
      <Panel title="By month" bodyless><TaxTable rows={D.by_month} first="Month" firstKey="month" extra={{ label: 'Invoices', key: 'count' }} /></Panel>
    </div>
    <Panel title="Invoices" bodyless>
      <Table head={['Invoice', 'Date', 'Customer', 'GSTIN', { label: 'Type', align: 'c' }, 'Place of supply',
        { label: 'Taxable', align: 'r' }, { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }, { label: 'IGST', align: 'r' },
        { label: 'Invoice value', align: 'r' }]} empty="No tax invoices in this period.">
        {D.rows.map(r => <tr key={r.id}>
          <td className="mono"><b>{r.doc_no}</b>{r.reverse_charge && <div className="fine">reverse charge</div>}</td>
          <td className="mono">{gd(r.doc_date)}</td><td>{r.customer}</td>
          <td className="mono fine">{r.gstin || '—'}</td>
          <td className="c"><Tag kind={r.kind === 'B2B' ? 'ok' : undefined}>{r.kind}</Tag></td>
          <td>{r.pos} {r.pos_name}<div className="fine">{r.supply}</div></td>
          <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.cgst)}</td>
          <td className="r mono">{inr(r.sgst)}</td><td className="r mono">{inr(r.igst)}</td>
          <td className="r mono"><b>{inr(r.total)}</b></td></tr>)}
        {D.rows.length > 0 && <tr><td colSpan={6}><b>Total</b></td><td className="r mono"><b>{inr(T.taxable)}</b></td>
          <td className="r mono"><b>{inr(T.cgst)}</b></td><td className="r mono"><b>{inr(T.sgst)}</b></td>
          <td className="r mono"><b>{inr(T.igst)}</b></td><td className="r mono"><b>{inr(T.total)}</b></td></tr>}
      </Table>
    </Panel>
    {D.cancelled.length > 0 && <Panel title={`Cancelled in this period — ${D.cancelled.length}`} bodyless>
      <Table head={['Invoice', 'Date', 'Customer', 'Reason']}>
        {D.cancelled.map(r => <tr key={r.doc_no}><td className="mono">{r.doc_no}</td><td className="mono">{gd(r.doc_date)}</td>
          <td>{r.customer}</td><td className="fine">{r.reason || '—'}</td></tr>)}
      </Table>
      <div className="panel-bd fine">Cancelled invoices are left out of the figures above. Their numbers are reported in GSTR-1 table 13.</div>
    </Panel>}
  </>)
}

/* ========================================================= GST — purchases */
export function GstPurchases({ period }) {
  const { api } = useAuth()
  const d = useLoad(() => api.gstPurchases(period), [period])
  if (d.loading) return <Loading />
  if (d.error) return <ErrorBox>{d.error}</ErrorBox>
  const D = d.data, T = D.totals
  return (<>
    <Panel title={`GST register — purchases · ${D.rows.length} vendor invoices`}>
      <Figures items={[['Taxable value', inr(T.taxable)], ['CGST', inr(T.cgst)], ['SGST', inr(T.sgst)], ['IGST', inr(T.igst)],
        ['Input GST', inr(T.tax)], ['Input tax credit', inr(D.itc.tax), true]]} />
      <div className="fine" style={{ marginTop: 8 }}>Credit is shown where the vendor is GST-registered and charged GST. It is
        from the invoices recorded here — check it against GSTR-2B before claiming.
        {D.no_itc_count > 0 && ` ${D.no_itc_count} invoice(s) carry no credit (unregistered vendor or no GST).`}</div>
    </Panel>
    <div className="grid2">
      <Panel title="By GST rate" bodyless><TaxTable rows={D.by_rate} first="Rate" firstKey="rate" /></Panel>
      <Panel title="By month" bodyless><TaxTable rows={D.by_month} first="Month" firstKey="month" extra={{ label: 'Invoices', key: 'count' }} /></Panel>
    </div>
    <Panel title="Vendor invoices" bodyless>
      <Table head={['Vendor invoice', 'Our no.', 'Date', 'Vendor', 'GSTIN', { label: 'Credit', align: 'c' },
        { label: 'Taxable', align: 'r' }, { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }, { label: 'IGST', align: 'r' },
        { label: 'Invoice value', align: 'r' }]} empty="No vendor invoices in this period.">
        {D.rows.map(r => <tr key={r.id}>
          <td className="mono"><b>{r.doc_no}</b></td><td className="mono fine">{r.our_no || '—'}</td>
          <td className="mono">{gd(r.doc_date)}</td><td>{r.vendor}<div className="fine">{r.supply}</div></td>
          <td className="mono fine">{r.gstin || 'unregistered'}</td>
          <td className="c">{r.itc ? <Tag kind="ok">ITC</Tag> : <Tag>None</Tag>}</td>
          <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.cgst)}</td>
          <td className="r mono">{inr(r.sgst)}</td><td className="r mono">{inr(r.igst)}</td>
          <td className="r mono"><b>{inr(r.total)}</b></td></tr>)}
        {D.rows.length > 0 && <tr><td colSpan={6}><b>Total</b></td><td className="r mono"><b>{inr(T.taxable)}</b></td>
          <td className="r mono"><b>{inr(T.cgst)}</b></td><td className="r mono"><b>{inr(T.sgst)}</b></td>
          <td className="r mono"><b>{inr(T.igst)}</b></td><td className="r mono"><b>{inr(T.total)}</b></td></tr>}
      </Table>
    </Panel>
  </>)
}

/* ================================================================ TDS */
export function TdsReport({ period }) {
  const { api } = useAuth()
  const d = useLoad(() => api.tdsReport(period), [period])
  if (d.loading) return <Loading />
  if (d.error) return <ErrorBox>{d.error}</ErrorBox>
  const V = d.data.vendors, C = d.data.customers
  const overdue = V.by_month.filter(m => m.status === 'Overdue')
  return (<>
    <Panel title="TDS — what we deducted from vendors (to deposit with the government)">
      <Figures items={[['TDS deducted', inr(V.total), true], ['Deductions', String(V.rows.length)],
        ['Still to deduct on unpaid invoices', inr(V.pending_total)]]} />
      {V.without_pan.length > 0 && <Alert kind="bad"><b>No PAN on file for {V.without_pan.join(', ')}.</b> Without a PAN,
        section 206AA calls for TDS at 20% or the section rate, whichever is higher.</Alert>}
      <div className="fine" style={{ marginTop: 8 }}>Deposit by challan ITNS 281 by the 7th of the following month (30 April for March).
        "Overdue" is against today; mark deposits in your challan records.</div>
    </Panel>
    <div className="grid2">
      <Panel title="By month — deposit due" bodyless>
        <Table head={['Month', { label: 'Deductions', align: 'r' }, { label: 'TDS', align: 'r' }, 'Deposit by', { label: '', align: 'c' }]} empty="No TDS deducted in this period.">
          {V.by_month.map(m => <tr key={m.month}><td>{monthLabel(m.month)}</td><td className="r mono">{m.count}</td>
            <td className="r mono"><b>{inr(m.tds)}</b></td><td className="mono">{gd(m.due_date)}</td>
            <td className="c"><Tag kind={m.status === 'Overdue' ? 'warn' : 'ok'}>{m.status}</Tag></td></tr>)}
        </Table>
        {overdue.length > 0 && <div className="panel-bd fine">Late deposit attracts interest at 1.5% a month under section 201(1A) — if these were deposited, ignore the flag.</div>}
      </Panel>
      <Panel title="By section" bodyless>
        <Table head={['Section', { label: 'TDS', align: 'r' }]} empty="—">
          {V.by_section.map(s => <tr key={s.section}><td className="mono">{s.section}</td><td className="r mono">{inr(s.tds)}</td></tr>)}
        </Table>
      </Panel>
    </div>
    <Panel title={`Deductions — ${V.rows.length}`} bodyless>
      <Table head={['Payment date', 'Vendor', 'PAN', 'Section', { label: 'Rate', align: 'r' }, 'Vendor invoice',
        { label: 'Taxable', align: 'r' }, { label: 'TDS', align: 'r' }, { label: 'Paid to vendor', align: 'r' }, 'Deposit by']}
        empty="No TDS deducted from vendors in this period.">
        {V.rows.map((r, i) => <tr key={i}>
          <td className="mono">{gd(r.pay_date)}</td><td>{r.vendor}<div className="fine mono">{r.vendor_code}</div></td>
          <td className="mono">{r.pan || <span style={{ color: 'var(--red)' }}>missing</span>}</td>
          <td className="mono">{r.section || '—'}</td><td className="r mono">{r.rate ? `${r.rate}%` : '—'}</td>
          <td className="mono">{r.invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
          <td className="r mono">{inr(r.taxable)}</td><td className="r mono"><b>{inr(r.tds)}</b></td>
          <td className="r mono">{inr(r.paid)}</td>
          <td className="mono fine">{gd(V.by_month.find(m => m.month === r.month)?.due_date)}</td></tr>)}
      </Table>
    </Panel>
    {V.pending.length > 0 && <Panel title={`TDS still to deduct — ${V.pending.length} unpaid invoice(s)`} bodyless>
      <Table head={['Vendor invoice', 'Vendor', 'Section', { label: 'Rate', align: 'r' }, { label: 'Taxable', align: 'r' },
        { label: 'Expected', align: 'r' }, { label: 'Deducted', align: 'r' }, { label: 'To deduct', align: 'r' }]}>
        {V.pending.map(r => <tr key={r.invoice + r.vendor}><td className="mono">{r.invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
          <td>{r.vendor}</td><td className="mono">{r.section || '—'}</td><td className="r mono">{r.rate}%</td>
          <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.expected)}</td>
          <td className="r mono">{inr(r.deducted)}</td><td className="r mono"><b>{inr(r.to_deduct)}</b></td></tr>)}
      </Table>
      <div className="panel-bd fine">From each vendor's TDS rate on the taxable value. It is deducted when you record the payment on Vendor Payments.</div>
    </Panel>}

    <Panel title="TDS — what customers deducted from us (to claim)">
      <Figures items={[['TDS deducted by customers', inr(C.total), true], ['Receipts', String(C.rows.length)]]} />
      <div className="fine" style={{ marginTop: 8 }}>This is credit against our own income tax once each customer files their
        TDS return. Match it to Form 26AS / AIS by customer and quarter, and ask for Form 16A.</div>
      {C.without_pan.length > 0 && <Alert kind="warn">No PAN on file for {C.without_pan.join(', ')} — needed to match Form 26AS.</Alert>}
    </Panel>
    <div className="grid2">
      <Panel title="By customer and quarter" bodyless>
        <Table head={['Quarter', 'Customer', 'PAN', { label: 'Receipts', align: 'r' }, { label: 'TDS', align: 'r' }]} empty="No TDS deducted by customers in this period.">
          {C.by_customer.map(r => <tr key={r.quarter + r.customer}><td>{r.quarter}</td><td>{r.customer}</td>
            <td className="mono">{r.pan || '—'}</td><td className="r mono">{r.count}</td><td className="r mono"><b>{inr(r.tds)}</b></td></tr>)}
        </Table>
      </Panel>
      <Panel title={`Receipts with TDS — ${C.rows.length}`} bodyless>
        <Table head={['Date', 'Customer', 'Invoice', { label: 'Received', align: 'r' }, { label: 'TDS', align: 'r' }]} empty="—">
          {C.rows.map((r, i) => <tr key={i}><td className="mono">{gd(r.date)}</td><td>{r.customer}</td>
            <td className="mono">{r.invoice}{r.reversal && <div className="fine">reversal</div>}</td>
            <td className="r mono">{inr(r.received)}</td><td className="r mono"><b>{inr(r.tds)}</b></td></tr>)}
        </Table>
      </Panel>
    </div>
  </>)
}
