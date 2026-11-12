import { Fragment, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { inr, gd } from '../lib/fmt'
import { Panel, Table, useLoad, Loading, ErrorBox } from './ui'
import RangePicker, { useRanges } from './RangePicker'
import { TransactionModal } from './Transactions'

/** The sales reports offered on Insight → Reports. */
export const SALES_REPORTS = [
  { key: 'sales_customer', group: 'customer', label: 'Sales by customer' },
  { key: 'sales_material', group: 'material', label: 'Sales by material' },
  { key: 'sales_employee', group: 'employee', label: 'Sales by employee (created by)' },
]

const sel = { padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }

function downloadCsv(rows, head, file) {
  const body = [head.join(','), ...rows.map(r => r.map(v =>
    `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))].join('\r\n')
  const url = URL.createObjectURL(new Blob(['\ufeff' + body], { type: 'text/csv' }))
  const a = document.createElement('a'); a.href = url; a.download = file; a.click()
  URL.revokeObjectURL(url)
}

/** +12.5% / −3.0% / new, coloured by direction. */
function Change({ pct, before }) {
  if (pct == null) return before ? <span className="fine">—</span> : <span className="chg up">new</span>
  const cls = pct > 0 ? 'up' : pct < 0 ? 'down' : ''
  return <span className={`chg ${cls}`}>{pct > 0 ? '+' : pct < 0 ? '−' : ''}{Math.abs(pct).toFixed(1)}%</span>
}

const rowName = (group, x) => group === 'customer' ? x.name
  : group === 'material' ? `${x.code} ${x.descr || ''}`.trim() : x.name

export default function SalesReport({ kind, selector }) {
  const { api } = useAuth()
  const group = SALES_REPORTS.find(r => r.key === kind).group
  const ranges = useRanges()

  const [period, setPeriod] = useState({ range: 'this_month' })
  const [compare, setCompare] = useState(false)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)      // row whose transactions are shown
  const [doc, setDoc] = useState(null)        // transaction open in the modal

  useEffect(() => { setOpen(null) }, [kind, period, compare])

  const report = useLoad(() => api.salesReport({ group, today: ranges.today, compare, ...period }),
    [group, period, compare])

  const d = report.data
  const T = d?.totals
  const C = d?.compare
  const totalKey = group === 'material' ? 'line_total' : 'total'

  const rows = useMemo(() => {
    if (!d) return []
    const s = q.trim().toLowerCase()
    if (!s) return d.rows
    return d.rows.filter(x => [x.name, x.code, x.descr, x.email, x.emp_code, x.emp_name, x.hsn]
      .filter(Boolean).join(' ').toLowerCase().includes(s))
  }, [d, q])
  const filtered = d && rows.length !== d.rows.length
  // Totals of the rows on screen, when a search hides some.
  const shown = useMemo(() => {
    const add = k => rows.reduce((a, x) => a + (x[k] || 0), 0)
    return { taxable: add('taxable'), tax: add('tax'), total: add('total'), qty: add('qty'),
      prev_total: add('prev_total'),
      invoices: new Set(rows.flatMap(x => x.docs.map(v => v.id))).size }
  }, [rows])

  const tag = d ? `${d.range.start}_to_${d.range.end}` : ''
  const money = x => Number(x || 0).toFixed(2)

  const exportCsv = () => {
    if (!d) return
    const extraHead = C ? ['Same period last year', 'Change %'] : []
    const extra = x => C ? [money(x.prev_total), x.growth_pct ?? ''] : []
    if (group === 'customer') downloadCsv(rows.map(x => [x.code, x.name, x.invoice_count,
      money(x.taxable), money(x.cgst), money(x.sgst), money(x.igst), money(x.tax), money(x.total), x.share_pct, ...extra(x)]),
      ['Customer code', 'Customer', 'Invoices', 'Taxable value', 'CGST', 'SGST', 'IGST', 'GST', 'Total', 'Share %', ...extraHead],
      `sales_by_customer_${tag}.csv`)
    else if (group === 'material') downloadCsv(rows.map(x => [x.code, x.descr, x.hsn, x.uom, x.qty,
      x.avg_price ?? '', x.invoice_count, money(x.taxable), money(x.cgst), money(x.sgst), money(x.igst),
      money(x.tax), money(x.total), x.share_pct, ...extra(x)]),
      ['Material', 'Description', 'HSN/SAC', 'UOM', 'Quantity', 'Average price', 'Invoices', 'Taxable value',
        'CGST', 'SGST', 'IGST', 'GST', 'Line value', 'Share %', ...extraHead], `sales_by_material_${tag}.csv`)
    else downloadCsv(rows.map(x => [x.name, x.email, x.emp_code, x.emp_name, x.invoice_count,
      money(x.taxable), money(x.cgst), money(x.sgst), money(x.igst), money(x.tax), money(x.total), x.share_pct, ...extra(x)]),
      ['Created by', 'E-mail', 'Employee ID', 'Employee name', 'Invoices', 'Taxable value', 'CGST', 'SGST',
        'IGST', 'GST', 'Total', 'Share %', ...extraHead], `sales_by_employee_${tag}.csv`)
  }

  // Every transaction behind every row, one line each.
  const exportDetail = () => {
    if (!d) return
    const by = { customer: 'Customer', material: 'Material', employee: 'Created by' }[group]
    const out = []
    for (const x of rows) for (const v of x.docs) out.push([rowName(group, x), v.doc_no, v.doc_date, v.customer,
      ...(group === 'material' ? [v.qty] : []), money(v.taxable), money(v.total)])
    downloadCsv(out, [by, 'Invoice', 'Date', 'Customer', ...(group === 'material' ? ['Quantity'] : []),
      'Taxable value', group === 'material' ? 'Line value' : 'Total'], `sales_by_${group}_transactions_${tag}.csv`)
  }

  const cmpHead = C ? [{ label: 'Last year', align: 'r' }, { label: 'Change', align: 'r' }] : []
  const head = {
    customer: ['', 'Customer', { label: 'Invoices', align: 'r' }, { label: 'Taxable value', align: 'r' },
      { label: 'GST', align: 'r' }, { label: 'Total', align: 'r' }, ...cmpHead, { label: 'Share', align: 'r' }],
    material: ['', 'Material', 'Description', 'UOM', { label: 'Quantity', align: 'r' },
      { label: 'Avg price', align: 'r' }, { label: 'Invoices', align: 'r' }, { label: 'Taxable value', align: 'r' },
      { label: 'GST', align: 'r' }, { label: 'Line value', align: 'r' }, ...cmpHead, { label: 'Share', align: 'r' }],
    employee: ['', 'Created by', 'Employee ID', { label: 'Invoices', align: 'r' },
      { label: 'Taxable value', align: 'r' }, { label: 'GST', align: 'r' }, { label: 'Total', align: 'r' },
      ...cmpHead, { label: 'Share', align: 'r' }],
  }[group]
  const ncols = head.length

  const toggle = k => setOpen(open === k ? null : k)

  const cells = x => {
    const cmp = C && <>
      <td className="r mono fine-num">{inr(x.prev_total)}</td>
      <td className="r mono"><Change pct={x.growth_pct} before={x.prev_total} /></td></>
    const share = <td className="r mono"><span className="sr-share">
      <span className="sr-bar"><span style={{ width: `${Math.min(100, x.share_pct)}%` }} /></span>
      {x.share_pct.toFixed(1)}%</span></td>
    if (group === 'customer') return <>
      <td><b>{x.name}</b><div className="fine mono">{x.code}{x.party_type ? ` ${x.party_type}` : ''}</div></td>
      <td className="r mono">{x.invoice_count}</td><td className="r mono">{inr(x.taxable)}</td>
      <td className="r mono">{inr(x.tax)}</td><td className="r mono"><b>{inr(x.total)}</b></td>{cmp}{share}</>
    if (group === 'material') return <>
      <td className="mono"><b>{x.code}</b></td><td>{x.descr}</td><td>{x.uom}</td>
      <td className="r mono">{x.qty}</td><td className="r mono">{x.avg_price == null ? '—' : inr(x.avg_price)}</td>
      <td className="r mono">{x.invoice_count}</td><td className="r mono">{inr(x.taxable)}</td>
      <td className="r mono">{inr(x.tax)}</td><td className="r mono"><b>{inr(x.total)}</b></td>{cmp}{share}</>
    return <>
      <td>{x.user_id ? <><b>{x.name}</b><div className="fine">{x.email}</div></>
        : <><b>{x.name}</b><div className="fine">{x.note}</div></>}</td>
      <td>{x.emp_code ? <><span className="mono">{x.emp_code}</span><div className="fine">{x.emp_name}</div></>
        : <span className="fine">{x.user_id ? 'Not on the employee master' : ''}</span>}</td>
      <td className="r mono">{x.invoice_count}</td><td className="r mono">{inr(x.taxable)}</td>
      <td className="r mono">{inr(x.tax)}</td><td className="r mono"><b>{inr(x.total)}</b></td>{cmp}{share}</>
  }

  // With a search, the total row adds up what is on screen; otherwise it is the server's.
  const S = filtered ? { ...shown, line_total: shown.total } : T && { ...T, prev_total: C?.totals?.[totalKey] }
  const cmpTot = C && <><td className="r mono">{inr(S.prev_total)}</td>
    <td className="r mono">{!filtered && <Change pct={C.growth_pct} before={S.prev_total} />}</td></>
  const label = filtered ? `Total of ${rows.length} shown` : 'Total'
  const totalRow = T && (group === 'material'
    ? <tr className="sr-total"><td /><td colSpan={3}>{label}</td><td className="r mono">{S.qty}</td><td />
      <td className="r mono">{S.invoices}</td><td className="r mono">{inr(S.taxable)}</td>
      <td className="r mono">{inr(S.tax)}</td><td className="r mono">{inr(S.line_total)}</td>{cmpTot}<td /></tr>
    : <tr className="sr-total"><td /><td colSpan={group === 'employee' ? 2 : 1}>{label}</td>
      <td className="r mono">{S.invoices}</td><td className="r mono">{inr(S.taxable)}</td>
      <td className="r mono">{inr(S.tax)}</td><td className="r mono">{inr(S.total)}</td>{cmpTot}<td /></tr>)

  const docs = x => {
    if (!x.docs.length) return <div className="fine" style={{ padding: '8px 4px' }}>
      No sales in this period. Last year: {x.prev_invoices} invoice{x.prev_invoices === 1 ? '' : 's'},
      ₹ {inr(x.prev_total)}.</div>
    const sum = k => x.docs.reduce((a, v) => a + (v[k] || 0), 0)
    return (
      <div className="scroll"><table className="sr-docs">
        <thead><tr><th>Invoice</th><th>Date</th>{group !== 'customer' && <th>Customer</th>}
          {group === 'material' && <th className="r">Quantity</th>}
          <th className="r">Taxable value</th><th className="r">{group === 'material' ? 'Line value' : 'Total'}</th>
          <th /></tr></thead>
        <tbody>{x.docs.map(v => <tr key={v.id} className="tx-row" tabIndex={0}
          onClick={() => setDoc({ id: v.id, from: rowName(group, x) })}
          onKeyDown={e => { if (e.key === 'Enter') setDoc({ id: v.id, from: rowName(group, x) }) }}>
          <td className="mono"><b>{v.doc_no}</b></td><td className="mono">{gd(v.doc_date)}</td>
          {group !== 'customer' && <td>{v.customer}</td>}
          {group === 'material' && <td className="r mono">{v.qty}</td>}
          <td className="r mono">{inr(v.taxable)}</td><td className="r mono">{inr(v.total)}</td>
          <td className="r"><span className="tx-open">Details ›</span></td></tr>)}
          <tr className="sr-docs-total"><td colSpan={group === 'customer' ? 2 : 3}>
            {x.docs.length} invoice{x.docs.length === 1 ? '' : 's'}</td>
            {group === 'material' && <td className="r mono">{sum('qty')}</td>}
            <td className="r mono">{inr(sum('taxable'))}</td><td className="r mono">{inr(sum('total'))}</td><td /></tr>
        </tbody>
      </table></div>)
  }

  return (<>
    <Panel title="Reports" right={<>
      {selector}
      <RangePicker value={period} onChange={setPeriod} ranges={ranges} />
      <label className="sr-compare">
        <input type="checkbox" checked={compare} onChange={e => setCompare(e.target.checked)} />
        Compare with a year earlier</label>
      <button className="btn btn-sm" onClick={exportCsv} disabled={!d || !rows.length}>Export CSV</button>
      <button className="btn btn-sm" onClick={exportDetail} disabled={!d || !rows.length}
        title="One line per invoice, under each row">Export transactions</button>
    </>} bodyless>

      {report.loading ? <Loading /> : report.error ? <div className="panel-bd"><ErrorBox>{report.error}</ErrorBox></div> : <>
        <div className="sr-head">
          <div className="sr-period">
            <span className="fine">Period</span>
            <b>{gd(d.range.start)} to {gd(d.range.end)}</b>
            <span className="fine">{d.range.label}</span>
            {C && <span className="fine">Compared with {gd(C.range.start)} to {gd(C.range.end)}
              {C.range.to_date ? ' (this period is still running, so both run to the same date)' : ''}</span>}
          </div>
          <div className="sr-kpi"><span className="fine">Invoices</span><b className="mono">{T.invoices}</b>
            {C && <span className="fine">last year {C.totals.invoices}</span>}</div>
          <div className="sr-kpi"><span className="fine">Taxable value</span><b className="mono">{inr(T.taxable)}</b>
            {C && <span className="fine">last year {inr(C.totals.taxable)}</span>}</div>
          <div className="sr-kpi"><span className="fine">GST</span><b className="mono">{inr(T.tax)}</b></div>
          <div className="sr-kpi"><span className="fine">Sales total</span><b className="mono">{inr(T.total)}</b>
            {C && <span className="fine">last year {inr(C.totals.total)} <Change pct={C.growth_pct}
              before={C.totals[totalKey]} /></span>}</div>
        </div>
        <div className="sr-tools">
          <input type="search" value={q} onChange={e => setQ(e.target.value)} style={{ ...sel, width: 240 }}
            placeholder={`Find a ${group === 'material' ? 'material' : group === 'customer' ? 'customer' : 'person'}`}
            aria-label="Search rows" />
          <span className="fine">{rows.length} of {d.rows.length} {group === 'material' ? 'materials'
            : group === 'customer' ? 'customers' : 'people'}. Select a row for its invoices, then an invoice for its details.</span>
        </div>
        <Table head={head} cols={ncols}
          empty={q ? 'Nothing matches that search.'
            : 'No tax invoices in this period. Proformas and cancelled invoices are not counted as sales.'}>
          {rows.length ? [
            ...rows.map(x => {
              const k = x.key
              return <Fragment key={k}>
                <tr className={`sr-row ${open === k ? 'row-open' : ''} ${x.only_before ? 'sr-gone' : ''}`}
                  onClick={() => toggle(k)}>
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
          Quarters and years follow your financial year. Weeks run Monday to Sunday, and a week compares with the
          same week 52 weeks earlier.
          {C && <> Rows in grey sold only in the earlier period.</>}
          {group === 'material' && T.roundoff !== 0 && <> Line values exclude invoice round-off of {inr(T.roundoff)},
            so they total {inr(T.line_total)} against invoice totals of {inr(T.total)}.</>}
          {group === 'employee' && <> “Created by” is the user who saved the invoice, matched to the employee master by
            e-mail. Invoices saved before this version show as Not recorded.</>}
        </div>
      </>}
    </Panel>
    {doc && <TransactionModal id={doc.id} onClose={() => setDoc(null)}
      onBack={() => setDoc(null)} backLabel={`Back to ${doc.from}`} />}
  </>)
}
