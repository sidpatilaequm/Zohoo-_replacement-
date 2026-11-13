import { useEffect, useState } from 'react'
import { useFy } from '../lib/fy'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons, PeriodPicker, useDefaultFy,
  FinancialYearPicker, DateRangePicker } from '../components/ui'
import { inr, money, gd } from '../lib/fmt'
import { GstSales, GstPurchases, TdsReport } from '../components/TaxReports'

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const label = p => { const [y, m] = p.split('-'); return `${MON[+m - 1]} ${y}` }

export default function Registers() {
  const { api } = useAuth()
  const periods = useLoad(() => api.periods())
  const fys = useLoad(() => api.financialYears())
  // v5.0: both open on the year chosen at the top, and follow it
  const top = useFy()
  const [period, setPeriod] = useState(top.param)
  const [financialYear, setFinancialYear] = useState(top.param)
  useEffect(() => { setPeriod(top.param); setFinancialYear(top.param) }, [top.param])
  const [dateRange, setDateRange] = useState('')
  const today = (() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })()
  const invoiceFilters = { financialYear, dateRange, today }
  const [which, setWhich] = useState('invoices')
  const [variant, setVariant] = usePrintVariant()
  const [printAs, setPrintAs] = useState('')
  const [flash, showFlash] = useFlash()
  const p = period || null
  const inv = useLoad(
    () => api.invoiceRegister(invoiceFilters),
    [financialYear, dateRange, today]
  )
  const gst = useLoad(() => api.gstRegister(p), [p])
  const tds = useLoad(() => api.tdsRegister(p), [p])
  const gtds = useLoad(() => api.gstTdsRegister(p), [p])       // v5.0 GST withheld
  const govt = useLoad(() => api.govtPayments(p), [p])          // v5.0 statutory payments

  if (periods.loading || fys.loading || period === undefined) return <Loading />
  const busy = inv.loading || gst.loading || tds.loading || gtds.loading || govt.loading
  const anyErr = inv.error || gst.error || tds.error || gtds.error || govt.error
  if (anyErr) return <ErrorBox>{anyErr}</ErrorBox>

  const csv = w => api.registerCsv(w, p).catch(x => showFlash(x.message, 'bad'))
  // v5.0: the two new registers are exported from what is on screen
  const localCsv = w => {
    const rows = w === 'govt'
      ? [['Date', 'Paid towards', 'For month', 'Challan', 'Details', 'Amount', 'Bank account', 'Bank narration'],
         ...govt.data.rows.map(r => [r.date, r.kind_label, r.for_month || '', r.challan_ref || '', r.descr || '', r.amount, r.account, r.bank_ref || ''])]
      : [['Side', 'Date', 'Party', 'GSTIN', 'Invoice', 'Invoice date', 'Taxable', 'Paid', 'TDS', 'GST withheld', 'Implied rate %', 'Source'],
         ...[['Customer', gtds.data.customers], ['Vendor', gtds.data.vendors]].flatMap(([side, rs]) => rs.map(r =>
           [side, r.date, r.party, r.gstin || '', r.invoice, r.invoice_date, r.taxable, r.paid, r.tds, r.gst_tds, r.implied_rate_pct, r.source]))]
    const text = rows.map(r => r.map(c => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
    a.download = `${w === 'govt' ? 'statutory-payments' : 'gst-withheld'}-${p || 'all'}.csv`
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }
  const controls = (<>
    <select value={which} onChange={e => setWhich(e.target.value)}
      style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      <option value="invoices">Invoice register</option>
      <option value="gst">GST register</option>
      <option value="tds">TDS register</option>
      <option value="gst-sales">GST register — sales</option>
      <option value="gst-purchases">GST register — purchases</option>
      <option value="tds-report">TDS report — vendors and customers</option>
      <option value="gst-tds">GST withheld (GST TDS)</option>
      <option value="govt">Statutory payments — GST, TDS, PF, ESI</option>
    </select>
    {which === 'invoices' ? (
      <>
        <FinancialYearPicker
          value={financialYear}
          onChange={setFinancialYear}
          years={fys.data || []}
        />
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </>
    ) : (
      <PeriodPicker
        value={period}
        onChange={setPeriod}
        months={periods.data || []}
        years={fys.data || []}
      />
    )}
    {which === 'tds-report'
      ? <><button type="button" className="btn btn-sm" onClick={() => csv('tds-vendors')}>CSV — vendors</button>
          <button type="button" className="btn btn-sm" onClick={() => csv('tds-customers')}>CSV — customers</button></>
      : ['gst-tds', 'govt'].includes(which)
        ? <button type="button" className="btn btn-sm" onClick={() => localCsv(which)}>Export CSV</button>
        : <button type="button" className="btn btn-sm" onClick={() => csv(which)}>Export CSV</button>}</>)

  if (busy) return <><Panel title="Registers" right={controls} /><Loading /></>

  return (<>
    {flash}
    <Panel title="Registers" right={controls}>
      <Alert kind="ok">These are the books as recorded here. They are the starting point for a
        return, not the return itself.</Alert>
    </Panel>

    {which === 'invoices' && (
      <Panel title={`Invoice register — ${inv.data.length} documents`} right={<>
        <VariantPicker value={variant} onChange={setVariant} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <span className="fine">Print as</span>
          <select value={printAs} onChange={e => setPrintAs(e.target.value)}
            style={{ padding: '6px 9px', border: '1px solid var(--line2)', borderRadius: 7 }}>
            <option value="">As recorded</option>
            <option value="PRO">Proforma invoice</option>
            <option value="TAX">Tax invoice</option>
          </select></label></>} bodyless>
        <Table head={[{ label: 'Type', align: 'c' }, 'Invoice', 'Date', 'Customer', 'GSTIN',
          'PAN', { label: 'MSME', align: 'c' }, { label: 'Supply', align: 'c' },
          { label: 'Taxable', align: 'r' }, { label: 'CGST', align: 'r' },
          { label: 'SGST', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'Total', align: 'r' }, { label: 'Outstanding', align: 'r' },
          { label: 'Print', align: 'c' }]}
          empty="Nothing in this period.">
          {inv.data.map((r, i) => (
            <tr key={i} style={r.status === 'CANCELLED' ? { opacity: .6 } : undefined}>
              <td className="c">{r.status === 'CANCELLED'
                ? <Tag kind="bad" title={r.cancel_reason}>CANCELLED</Tag>
                : r.doc_type === 'Proforma'
                ? <Tag kind="warn">PRO</Tag> : <Tag kind="ok">TAX</Tag>}</td>
              <td className="mono"><b>{r.doc_no}</b></td>
              <td className="mono">{gd(r.doc_date)}</td>
              <td>{r.customer}<div className="fine mono">{r.customer_code}</div></td>
              <td className="mono">{r.gstin || '—'}</td>
              <td className="mono">{r.pan || '—'}</td>
              <td className="c">{r.msme ? <Tag kind="ok">Yes</Tag> : <Tag>No</Tag>}</td>
              <td className="c">{r.supply === 'Intra-state'
                ? <Tag kind="ok">Intra</Tag> : <Tag kind="warn">Inter</Tag>}</td>
              <td className="r mono">{inr(r.taxable)}</td>
              <td className="r mono">{inr(r.cgst)}</td><td className="r mono">{inr(r.sgst)}</td>
              <td className="r mono">{inr(r.igst)}</td>
              <td className="r mono"><b>{inr(r.total)}</b></td>
              <td className="r mono">{r.outstanding === null || r.status === 'CANCELLED' ? '—' : inr(r.outstanding)}</td>
              <td className="c"><PrintButtons kind="invoices" id={r.id} variant={variant}
                extra={printAs ? `&as=${printAs}` : ''} onError={m => showFlash(m, 'bad')} /></td>
            </tr>))}
        </Table>
      </Panel>)}

    {which === 'gst' && (<>
      <Panel title="GST register — position" bodyless>
        <Table head={['', { label: 'Taxable', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]}>
          <tr><td>Outward supplies</td>
            <td className="r mono">{inr(gst.data.totals.outward.taxable)}</td>
            <td className="r mono">{inr(gst.data.totals.outward.igst)}</td>
            <td className="r mono">{inr(gst.data.totals.outward.cgst)}</td>
            <td className="r mono">{inr(gst.data.totals.outward.sgst)}</td></tr>
          <tr><td>Input tax credit</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.taxable)}</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.igst)}</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.cgst)}</td>
            <td className="r mono">{inr(gst.data.totals.input_credit.sgst)}</td></tr>
          <tr style={{ background: 'var(--accent-soft)' }}>
            <td><b>Net payable</b></td><td className="r mono">—</td>
            <td className="r mono"><b>{inr(gst.data.totals.net_payable.igst)}</b></td>
            <td className="r mono"><b>{inr(gst.data.totals.net_payable.cgst)}</b></td>
            <td className="r mono"><b>{inr(gst.data.totals.net_payable.sgst)}</b></td></tr>
        </Table>
        <div className="panel-bd"><Alert kind="warn">{gst.data.note}</Alert></div>
      </Panel>
      <Panel title={`Outward — ${gst.data.outward.length}`} bodyless>
        <Table head={['Document', 'Date', 'Party', 'GSTIN', { label: 'Section', align: 'c' },
          { label: 'Taxable', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]} empty="Nothing outward.">
          {gst.data.outward.map((r, i) => (
            <tr key={i}><td className="mono"><b>{r.doc_no}</b></td>
              <td className="mono">{gd(r.doc_date)}</td><td>{r.party}</td>
              <td className="mono">{r.gstin || '—'}</td>
              <td className="c"><Tag kind={r.section === 'b2b' ? 'ok' : 'warn'}>{r.section}</Tag></td>
              <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.igst)}</td>
              <td className="r mono">{inr(r.cgst)}</td><td className="r mono">{inr(r.sgst)}</td>
            </tr>))}
        </Table>
      </Panel>
      <Panel title={`Inward — ${gst.data.inward.length}`} bodyless>
        <Table head={['Document', 'Date', 'Party', 'GSTIN', { label: 'Credit', align: 'c' },
          { label: 'Taxable', align: 'r' }, { label: 'IGST', align: 'r' },
          { label: 'CGST', align: 'r' }, { label: 'SGST', align: 'r' }]} empty="Nothing inward.">
          {gst.data.inward.map((r, i) => (
            <tr key={i}><td className="mono"><b>{r.doc_no}</b></td>
              <td className="mono">{gd(r.doc_date)}</td><td>{r.party}</td>
              <td className="mono">{r.gstin || '—'}</td>
              <td className="c">{r.registered
                ? <Tag kind="ok">claimable</Tag> : <Tag>unregistered</Tag>}</td>
              <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.igst)}</td>
              <td className="r mono">{inr(r.cgst)}</td><td className="r mono">{inr(r.sgst)}</td>
            </tr>))}
        </Table>
      </Panel>
    </>)}

    {which === 'gst-sales' && <GstSales period={p} />}
    {which === 'gst-purchases' && <GstPurchases period={p} />}
    {which === 'tds-report' && <TdsReport period={p} />}

    {which === 'gst-tds' && (<>
      <Panel title={`GST withheld by customers — ${money(gtds.data.customer_total)} to claim`} bodyless>
        <Table head={['Date', 'Customer', 'GSTIN', 'Invoice', { label: 'Taxable', align: 'r' },
          { label: 'Received', align: 'r' }, { label: 'TDS', align: 'r' }, { label: 'GST withheld', align: 'r' },
          { label: 'Implied rate', align: 'r' }, 'Source']}
          empty="No customer withheld GST in this period.">
          {gtds.data.customers.map((r, i) => (
            <tr key={i}>
              <td className="mono">{gd(r.date)}</td><td>{r.party}</td><td className="mono">{r.gstin || '—'}</td>
              <td className="mono">{r.invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
              <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.paid)}</td>
              <td className="r mono">{inr(r.tds)}</td><td className="r mono"><b>{inr(r.gst_tds)}</b></td>
              <td className="r mono">{r.implied_rate_pct}%</td>
              <td className="fine">{r.source}{r.bank_account && <div>{r.bank_account}</div>}</td>
            </tr>))}
        </Table>
        <div className="panel-bd"><div className="fine">Claim this in GSTR-2X; it then comes into the
          electronic cash ledger.</div></div>
      </Panel>
      <Panel title={`GST we withheld from vendors — ${money(gtds.data.vendor_total)} to pay over`} bodyless>
        <Table head={['Date', 'Vendor', 'GSTIN', 'Vendor invoice', { label: 'Taxable', align: 'r' },
          { label: 'Paid', align: 'r' }, { label: 'TDS', align: 'r' }, { label: 'GST withheld', align: 'r' },
          { label: 'Implied rate', align: 'r' }, 'Source']}
          empty="No GST was withheld from a vendor in this period.">
          {gtds.data.vendors.map((r, i) => (
            <tr key={i}>
              <td className="mono">{gd(r.date)}</td><td>{r.party}</td><td className="mono">{r.gstin || '—'}</td>
              <td className="mono">{r.invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
              <td className="r mono">{inr(r.taxable)}</td><td className="r mono">{inr(r.paid)}</td>
              <td className="r mono">{inr(r.tds)}</td><td className="r mono"><b>{inr(r.gst_tds)}</b></td>
              <td className="r mono">{r.implied_rate_pct}%</td>
              <td className="fine">{r.source}{r.bank_account && <div>{r.bank_account}</div>}</td>
            </tr>))}
        </Table>
        <div className="panel-bd"><Alert kind="warn">{gtds.data.note}</Alert></div>
      </Panel></>)}

    {which === 'govt' && (
      <Panel title={`Statutory payments — ${money(govt.data.total)}`} bodyless>
        <div className="panel-bd" style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {govt.data.by_kind.map(k => <span key={k.kind} className="chip"><span className="chip-k">{k.label}</span>
            <span className="mono">{inr(k.amount)}</span></span>)}
        </div>
        <Table head={['Date', 'Paid towards', 'For month', 'Challan', 'Details', { label: 'Amount', align: 'r' },
          'Bank account']}
          empty="No payment to the government is attached on Bank Statements in this period. Attach a challan payment to its bank debit under Government filings.">
          {govt.data.rows.map(r => (
            <tr key={r.id}>
              <td className="mono">{gd(r.date)}</td><td><b>{r.kind_label}</b></td>
              <td className="mono">{r.for_month || '—'}</td><td className="mono">{r.challan_ref || '—'}</td>
              <td className="fine">{r.descr}{r.notes && <div>{r.notes}</div>}</td>
              <td className="r mono"><b>{inr(r.amount)}</b></td>
              <td className="fine">{r.account}<div className="mono">{r.bank_ref}</div></td>
            </tr>))}
        </Table>
      </Panel>)}

    {which === 'tds' && (
      <Panel title={`TDS we deducted from vendors — ${money(tds.data.total_tds)} to deposit`} bodyless>
        <Table head={['Payment date', 'Vendor', 'PAN', { label: 'MSME', align: 'c' },
          'Vendor invoice', { label: 'Taxable', align: 'r' }, { label: 'Gross', align: 'r' },
          { label: 'TDS', align: 'r' }, { label: 'Paid', align: 'r' },
          { label: 'Implied rate', align: 'r' }, 'Source']}
          empty="No tax was deducted in this period.">
          {tds.data.rows.map((r, i) => (
            <tr key={i}>
              <td className="mono">{gd(r.pay_date)}</td>
              <td>{r.vendor}<div className="fine mono">{r.vendor_code}</div></td>
              <td className="mono">{r.pan || <span style={{ color: 'var(--red)' }}>missing</span>}</td>
              <td className="c">{r.msme
                ? <Tag kind="ok">{r.msme_number || 'Yes'}</Tag> : <Tag>No</Tag>}</td>
              <td className="mono">{r.vendor_invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
              <td className="r mono">{inr(r.invoice_taxable)}</td>
              <td className="r mono">{inr(r.gross)}</td>
              <td className="r mono"><b>{inr(r.tds)}</b></td>
              <td className="r mono">{inr(r.paid)}</td>
              <td className="r mono">{r.implied_rate_pct}%</td>
              <td className="fine">{r.source}{r.bank_ref &&
                <div className="mono">{r.bank_ref}</div>}</td>
            </tr>))}
        </Table>
        <div className="panel-bd">
          {tds.data.vendors_without_pan.length > 0 && <Alert kind="bad">
            <b>No PAN on file for {tds.data.vendors_without_pan.join(', ')}.</b> Section 206AA
            requires a higher rate where the deductee has not furnished a PAN.</Alert>}
          <Alert kind="warn">{tds.data.note}</Alert>
        </div>
      </Panel>)}

    {which === 'tds' && (
      <Panel title={`TDS deducted by customers — ${money(tds.data.customer_total_tds)} to claim`} bodyless>
        <Table head={['Date', 'Customer', 'PAN', 'Invoice', { label: 'Invoice value', align: 'r' },
          { label: 'Received', align: 'r' }, { label: 'TDS', align: 'r' },
          { label: 'Implied rate', align: 'r' }, 'Quarter', 'Source']}
          empty="No customer deducted tax in this period.">
          {tds.data.customers.map((r, i) => (
            <tr key={i}>
              <td className="mono">{gd(r.date)}</td>
              <td>{r.customer}<div className="fine mono">{r.customer_code}</div></td>
              <td className="mono">{r.pan || <span style={{ color: 'var(--red)' }}>missing</span>}</td>
              <td className="mono">{r.invoice}<div className="fine">{gd(r.invoice_date)}</div></td>
              <td className="r mono">{inr(r.invoice_total)}</td>
              <td className="r mono">{inr(r.received)}</td>
              <td className="r mono"><b>{inr(r.tds)}</b></td>
              <td className="r mono">{r.implied_rate_pct}%</td>
              <td>{r.quarter}</td>
              <td className="fine">{r.source}{r.bank_account &&
                <div>{r.bank_account}</div>}</td>
            </tr>))}
        </Table>
        <div className="panel-bd">
          {tds.data.customers_without_pan.length > 0 && <Alert kind="warn">
            No PAN on file for {tds.data.customers_without_pan.join(', ')} — needed to match
            Form 26AS.</Alert>}
          <div className="fine">Where an invoice is settled from the bank statement, the invoice
            value less the money collected is booked as TDS on the transaction that closed it.
            Match these to Form 26AS / AIS by customer and quarter, and ask for Form 16A.</div>
        </div>
      </Panel>)}
  </>)
}
