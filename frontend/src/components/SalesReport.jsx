import { Fragment, useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { inr, gd } from '../lib/fmt'
import { Panel, Table, useLoad, Loading, ErrorBox } from './ui'

/** The three sales reports offered on Insight → Reports. */
export const SALES_REPORTS = [
  { key: 'sales_customer', group: 'customer', label: 'Sales by customer' },
  { key: 'sales_material', group: 'material', label: 'Sales by material' },
  { key: 'sales_employee', group: 'employee', label: 'Sales by employee (created by)' },
]

// The browser's own date, so "Today" means today where the user is.
const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const monthStart = () => localToday().slice(0, 8) + '01'

const sel = { padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }

function downloadCsv(rows, head, file) {
  const body = [head.join(','), ...rows.map(r => r.map(v =>
    `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))].join('\r\n')
  const url = URL.createObjectURL(new Blob(['\ufeff' + body], { type: 'text/csv' }))
  const a = document.createElement('a'); a.href = url; a.download = file; a.click()
  URL.revokeObjectURL(url)
}

export default function SalesReport({ kind, selector }) {
  const { api } = useAuth()
  const group = SALES_REPORTS.find(r => r.key === kind).group
  const today = localToday()

  const ranges = useLoad(() => api.salesRanges(today), [])
  const [range, setRange] = useState('this_month')
  const [start, setStart] = useState(monthStart())
  const [end, setEnd] = useState(today)
  // What the report was last run with; custom dates only run on "Run report".
  const [run, setRun] = useState({ range: 'this_month' })
  const [open, setOpen] = useState(null)

  useEffect(() => { setOpen(null) }, [kind, run])

  const report = useLoad(() => api.salesReport({ group, today, ...run }), [group, run])

  const pickRange = (k) => {
    setRange(k)
    if (k !== 'custom') setRun({ range: k })
  }
  const runCustom = () => {
    if (!start || !end) return
    setRun({ range: 'custom', start, end })
  }
  const customInvalid = !start || !end || start > end

  const d = report.data
  const T = d?.totals

  const exportCsv = () => {
    if (!d) return
    const r = d.range
    const tag = `${r.start}_to_${r.end}`
    const money = x => Number(x || 0).toFixed(2)
    if (group === 'customer') downloadCsv(d.rows.map(x => [x.code, x.name, x.invoice_count,
      money(x.taxable), money(x.cgst), money(x.sgst), money(x.igst), money(x.tax), money(x.total), x.share_pct]),
      ['Customer code', 'Customer', 'Invoices', 'Taxable value', 'CGST', 'SGST', 'IGST', 'GST', 'Total', 'Share %'],
      `sales_by_customer_${tag}.csv`)
    else if (group === 'material') downloadCsv(d.rows.map(x => [x.code, x.descr, x.hsn, x.uom, x.qty,
      x.avg_price ?? '', x.invoice_count, money(x.taxable), money(x.cgst), money(x.sgst), money(x.igst),
      money(x.tax), money(x.total), x.share_pct]),
      ['Material', 'Description', 'HSN/SAC', 'UOM', 'Quantity', 'Average price', 'Invoices', 'Taxable value',
        'CGST', 'SGST', 'IGST', 'GST', 'Line value', 'Share %'], `sales_by_material_${tag}.csv`)
    else downloadCsv(d.rows.map(x => [x.name, x.email, x.emp_code, x.emp_name, x.invoice_count,
      money(x.taxable), money(x.cgst), money(x.sgst), money(x.igst), money(x.tax), money(x.total), x.share_pct]),
      ['Created by', 'E-mail', 'Employee ID', 'Employee name', 'Invoices', 'Taxable value', 'CGST', 'SGST',
        'IGST', 'GST', 'Total', 'Share %'], `sales_by_employee_${tag}.csv`)
  }

  const head = {
    customer: ['', 'Customer', { label: 'Invoices', align: 'r' }, { label: 'Taxable value', align: 'r' },
      { label: 'GST', align: 'r' }, { label: 'Total', align: 'r' }, { label: 'Share', align: 'r' }],
    material: ['', 'Material', 'Description', 'UOM', { label: 'Quantity', align: 'r' },
      { label: 'Avg price', align: 'r' }, { label: 'Invoices', align: 'r' }, { label: 'Taxable value', align: 'r' },
      { label: 'GST', align: 'r' }, { label: 'Line value', align: 'r' }, { label: 'Share', align: 'r' }],
    employee: ['', 'Created by', 'Employee ID', { label: 'Invoices', align: 'r' },
      { label: 'Taxable value', align: 'r' }, { label: 'GST', align: 'r' }, { label: 'Total', align: 'r' },
      { label: 'Share', align: 'r' }],
  }[group]
  const ncols = head.length

  const rowKey = x => x.code ?? x.user_id ?? 'none'
  const toggle = k => setOpen(open === k ? null : k)

  const cells = x => {
    const share = <td className="r mono"><span className="sr-share">
      <span className="sr-bar"><span style={{ width: `${Math.min(100, x.share_pct)}%` }} /></span>
      {x.share_pct.toFixed(1)}%</span></td>
    if (group === 'customer') return <>
      <td><b>{x.name}</b><div className="fine mono">{x.code}{x.party_type ? ` ${x.party_type}` : ''}</div></td>
      <td className="r mono">{x.invoice_count}</td><td className="r mono">{inr(x.taxable)}</td>
      <td className="r mono">{inr(x.tax)}</td><td className="r mono"><b>{inr(x.total)}</b></td>{share}</>
    if (group === 'material') return <>
      <td className="mono"><b>{x.code}</b></td><td>{x.descr}</td><td>{x.uom}</td>
      <td className="r mono">{x.qty}</td><td className="r mono">{x.avg_price == null ? '—' : inr(x.avg_price)}</td>
      <td className="r mono">{x.invoice_count}</td><td className="r mono">{inr(x.taxable)}</td>
      <td className="r mono">{inr(x.tax)}</td><td className="r mono"><b>{inr(x.total)}</b></td>{share}</>
    return <>
      <td>{x.user_id ? <><b>{x.name}</b><div className="fine">{x.email}</div></>
        : <><b>{x.name}</b><div className="fine">{x.note}</div></>}</td>
      <td>{x.emp_code ? <><span className="mono">{x.emp_code}</span><div className="fine">{x.emp_name}</div></>
        : <span className="fine">{x.user_id ? 'Not on the employee master' : ''}</span>}</td>
      <td className="r mono">{x.invoice_count}</td><td className="r mono">{inr(x.taxable)}</td>
      <td className="r mono">{inr(x.tax)}</td><td className="r mono"><b>{inr(x.total)}</b></td>{share}</>
  }

  const totalRow = T && (group === 'material'
    ? <tr className="sr-total"><td /><td colSpan={3}>Total</td><td className="r mono">{T.qty}</td><td />
      <td className="r mono">{T.invoices}</td><td className="r mono">{inr(T.taxable)}</td>
      <td className="r mono">{inr(T.tax)}</td><td className="r mono">{inr(T.line_total)}</td><td /></tr>
    : <tr className="sr-total"><td /><td colSpan={group === 'employee' ? 2 : 1}>Total</td>
      <td className="r mono">{T.invoices}</td><td className="r mono">{inr(T.taxable)}</td>
      <td className="r mono">{inr(T.tax)}</td><td className="r mono">{inr(T.total)}</td><td /></tr>)

  const docs = x => (
    <table className="sr-docs">
      <thead><tr><th>Invoice</th><th>Date</th>{group !== 'customer' && <th>Customer</th>}
        {group === 'material' && <th className="r">Quantity</th>}
        <th className="r">Taxable value</th><th className="r">{group === 'material' ? 'Line value' : 'Total'}</th></tr></thead>
      <tbody>{x.docs.map(v => <tr key={v.id}>
        <td className="mono">{v.doc_no}</td><td className="mono">{gd(v.doc_date)}</td>
        {group !== 'customer' && <td>{v.customer}</td>}
        {group === 'material' && <td className="r mono">{v.qty}</td>}
        <td className="r mono">{inr(v.taxable)}</td><td className="r mono">{inr(v.total)}</td></tr>)}</tbody>
    </table>)

  return (
    <Panel title="Reports" right={<>
      {selector}
      <select value={range} onChange={e => pickRange(e.target.value)} style={sel} aria-label="Date range">
        {(ranges.data || [{ key: 'this_month', name: 'This month' }]).map(r =>
          <option key={r.key} value={r.key}>{r.name}</option>)}
      </select>
      {range === 'custom' && <>
        <input type="date" value={start} max={end || undefined} onChange={e => setStart(e.target.value)}
          style={sel} aria-label="Start date" />
        <span className="fine">to</span>
        <input type="date" value={end} min={start || undefined} onChange={e => setEnd(e.target.value)}
          style={sel} aria-label="End date" />
        <button className="btn btn-sm btn-a" onClick={runCustom} disabled={customInvalid}>Run report</button>
      </>}
      <button className="btn btn-sm" onClick={exportCsv} disabled={!d || !d.rows.length}>Export CSV</button>
    </>} bodyless>

      {report.loading ? <Loading /> : report.error ? <div className="panel-bd"><ErrorBox>{report.error}</ErrorBox></div> : <>
        <div className="sr-head">
          <div className="sr-period">
            <span className="fine">Period</span>
            <b>{gd(d.range.start)} to {gd(d.range.end)}</b>
            <span className="fine">{d.range.label}{range === 'custom' && run.range !== 'custom'
              ? ' (choose dates and select Run report)' : ''}</span>
          </div>
          <div className="sr-kpi"><span className="fine">Invoices</span><b className="mono">{T.invoices}</b></div>
          <div className="sr-kpi"><span className="fine">Taxable value</span><b className="mono">{inr(T.taxable)}</b></div>
          <div className="sr-kpi"><span className="fine">GST</span><b className="mono">{inr(T.tax)}</b></div>
          <div className="sr-kpi"><span className="fine">Sales total</span><b className="mono">{inr(T.total)}</b></div>
        </div>
        <Table head={head} cols={ncols}
          empty="No tax invoices in this period. Proformas and cancelled invoices are not counted as sales.">
          {d.rows.length ? [
            ...d.rows.map(x => {
              const k = rowKey(x)
              return <Fragment key={k}>
                <tr className={`sr-row ${open === k ? 'row-open' : ''}`} onClick={() => toggle(k)}>
                  <td className="sr-tog"><button type="button" className="rm" aria-expanded={open === k}
                    aria-label={open === k ? 'Hide invoices' : 'Show invoices'}
                    onClick={e => { e.stopPropagation(); toggle(k) }}>{open === k ? '−' : '+'}</button></td>
                  {cells(x)}
                </tr>
                {open === k && <tr className="row-attach"><td colSpan={ncols}>{docs(x)}</td></tr>}
              </Fragment>
            }),
            <Fragment key="total">{totalRow}</Fragment>,
          ] : []}
        </Table>
        <div className="panel-bd fine">
          Sales are tax invoices dated in the period; proformas are left out and cancelled invoices reverse their sale.
          Quarters and years follow your financial year.
          {group === 'material' && T.roundoff !== 0 && <> Line values exclude invoice round-off of {inr(T.roundoff)},
            so they total {inr(T.line_total)} against invoice totals of {inr(T.total)}.</>}
          {group === 'employee' && <> “Created by” is the user who saved the invoice, matched to the employee master by
            e-mail. Invoices saved before this version show as Not recorded.</>}
          {' '}Select a row to see its invoices.
        </div>
      </>}
    </Panel>
  )
}
