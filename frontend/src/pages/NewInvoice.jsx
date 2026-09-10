import { useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, today } from '../lib/fmt'

export default function NewInvoice() {
  const { api, me } = useAuth()
  const customers = useLoad(() => api.customers())
  const materials = useLoad(() => api.materials())
  const states = useLoad(() => api.states())
  const [h, setH] = useState({ doc_type: 'TAX', doc_date: today(), due_date: '',
    customer_id: '', gstin: '', pos_state: '', po_no: '', po_date: '', reverse_chg: 'N',
    subject: '', instructions: '' })
  const trading = me?.tenant?.company_type === 'TRADING'
  const [lines, setLines] = useState([])
  const [pick, setPick] = useState('')
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setH(s => ({ ...s, [k]: v }))

  const cust = customers.data?.find(c => c.id === Number(h.customer_id))
  const regs = cust?.gstins || []
  const reg = regs.find(r => r.gstin === h.gstin) || regs.find(r => r.is_default) || regs[0]
  const pos = h.pos_state || reg?.state_code || cust?.bill_state
  const orgState = me?.tenant?.state_code
  const intra = pos === orgState

  const calc = useMemo(() => {
    let taxable = 0, cgst = 0, sgst = 0, igst = 0
    const rows = lines.map(l => {
      const m = materials.data?.find(x => x.id === l.material_id)
      if (!m) return null
      const amount = Math.round(Number(l.qty) * Number(l.price) * 100) / 100
      const c = intra ? Math.round(amount * m.cgst_pct) / 100 : 0
      const s = intra ? Math.round(amount * m.sgst_pct) / 100 : 0
      const i = intra ? 0 : Math.round(amount * m.igst_pct) / 100
      taxable += amount; cgst += c; sgst += s; igst += i
      return { ...l, m, amount, c, s, i, rate: intra ? m.cgst_pct + m.sgst_pct : m.igst_pct }
    }).filter(Boolean)
    const total = taxable + cgst + sgst + igst
    const rounded = Math.round(total)
    return { rows, taxable, cgst, sgst, igst, total, rounded, roundoff: rounded - total }
  }, [lines, materials.data, intra])

  function addLine() {
    const m = materials.data.find(x => x.id === Number(pick))
    if (!m) return
    setLines([...lines, { material_id: m.id, qty: 1, price: m.price }])
  }
  const problems = []
  if (!h.customer_id) problems.push('Select a customer.')
  if (!lines.length) problems.push('Add at least one line.')
  lines.forEach((l, i) => {
    const m = materials.data?.find(x => x.id === l.material_id)
    if (Number(l.qty) <= 0) problems.push(`Line ${i + 1}: quantity must be more than zero.`)
    else if (trading && m && Number(l.qty) > m.stock_qty) problems.push(`Line ${i + 1}: exceeds stock of ${m.stock_qty}.`)
    if (Number(l.price) <= 0) problems.push(`Line ${i + 1}: price must be more than zero.`)
  })
  if (h.po_date && h.po_date > h.doc_date) problems.push('PO date cannot be after the invoice date.')

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const d = await api.addInvoice({ ...h, customer_id: Number(h.customer_id),
        due_date: h.due_date || null, po_date: h.po_date || null,
        gstin: reg?.gstin || null, pos_state: pos,
        subject: h.subject || null, instructions: h.instructions || null,
        lines: lines.map(l => ({ material_id: l.material_id, qty: Number(l.qty),
          price: Number(l.price), descr2: l.descr2 || null })) })
      showFlash(`${h.doc_type === 'PRO' ? 'Proforma' : 'Invoice'} ${d.doc_no} saved — ${money(d.totals.rounded)}.`)
      setLines([]); setH(s => ({ ...s, customer_id: '', gstin: '', pos_state: '', po_no: '', po_date: '', subject: '', instructions: '' }))
      materials.reload()
    } catch (x) { setErr(x.message) }
  }
  if (customers.loading || materials.loading || states.loading) return <Loading />
  if (customers.error) return <ErrorBox>{customers.error}</ErrorBox>
  const stateName = c => states.data?.find(s => s.code === c)?.name || c

  return (<form onSubmit={save}>
    {flash}
    <Panel title="Invoice header">
      <div className="row">
        <Field label="Document type"
          hint={h.doc_type === 'PRO' ? 'Not a tax document — excluded from GST returns' : 'Counts towards GST returns'}>
          <select value={h.doc_type} onChange={e => set('doc_type', e.target.value)}>
            <option value="TAX">Tax invoice</option><option value="PRO">Proforma invoice</option>
          </select></Field>
        <Field label="Customer"><select value={h.customer_id}
          onChange={e => { set('customer_id', e.target.value); set('gstin', ''); set('pos_state', '') }}>
          <option value="">— select —</option>
          {customers.data.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
        </select></Field>
        <Field label="GST registration"
          hint={!cust ? 'Select a customer first' : regs.length === 0 ? 'B2C — no GSTIN'
            : regs.length === 1 ? 'Only one on file' : `${regs.length} registrations`}>
          <select value={reg?.gstin || ''} disabled={regs.length < 2}
            onChange={e => { set('gstin', e.target.value)
              const r = regs.find(x => x.gstin === e.target.value)
              if (r) set('pos_state', r.state_code) }}>
            {regs.length ? regs.map(r => <option key={r.id} value={r.gstin}>
              {r.gstin} · {stateName(r.state_code)}{r.label ? ' · ' + r.label : ''}</option>)
              : <option value="">Unregistered</option>}
          </select></Field>
        <Field label="Invoice date"><input type="date" value={h.doc_date}
          onChange={e => set('doc_date', e.target.value)} required /></Field>
        <Field label="Due date"><input type="date" value={h.due_date}
          onChange={e => set('due_date', e.target.value)} /></Field>
      </div>
      <div className="row" style={{ marginTop: 13 }}>
        <Field label="PO number"><input className="mono" value={h.po_no}
          onChange={e => set('po_no', e.target.value)} /></Field>
        <Field label="PO date"><input type="date" value={h.po_date}
          onChange={e => set('po_date', e.target.value)} /></Field>
        <Field label="Place of supply" hint="Defaults from the registration">
          <select value={pos || ''} onChange={e => set('pos_state', e.target.value)}>
            {states.data.map(s => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
          </select></Field>
        <Field label="Reverse charge"><select value={h.reverse_chg}
          onChange={e => set('reverse_chg', e.target.value)}>
          <option value="N">N — no</option><option value="Y">Y — yes</option></select></Field>
      </div>
      <div className="row" style={{ marginTop: 13 }}>
        <Field label="Subject" hint="Printed under Bill To / Ship To"><input value={h.subject}
          onChange={e => set('subject', e.target.value)} maxLength={200} /></Field>
      </div>
      <Field label="Specific instructions for this invoice" hint="Printed as Notes on the invoice, above the terms and bank details">
        <textarea value={h.instructions} onChange={e => set('instructions', e.target.value)} rows={3} maxLength={2000}
          style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--line2)', borderRadius: 7, font: 'inherit' }}
          placeholder="e.g. Thanks for your business. Pay immediately for licence activation." /></Field>
      {cust && <Alert kind={intra ? 'ok' : 'warn'}>
        <b>{cust.name}</b> · GSTIN {reg?.gstin || 'unregistered'}<br />
        Place of supply {pos} — {stateName(pos)}. {intra
          ? 'Intra-state, so CGST and SGST apply and IGST is nil.'
          : 'Inter-state, so IGST applies and CGST and SGST are nil.'}
      </Alert>}
    </Panel>

    <Panel title="Items" right={<>
      <select value={pick} onChange={e => setPick(e.target.value)}
        style={{ padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7, minWidth: 250 }}>
        <option value="">— select a material —</option>
        {materials.data.map(m => <option key={m.id} value={m.id}>{m.code} · {m.descr}</option>)}
      </select>
      <button type="button" className="btn btn-sm btn-a" onClick={addLine}>Add item</button></>} bodyless>
      <Table head={['#', 'Material', 'Description 2', 'HSN', { label: 'Quantity', align: 'r' },
        { label: 'UoM', align: 'c' }, { label: 'Unit price', align: 'r' },
        { label: 'Amount', align: 'r' }, { label: 'Tax %', align: 'r' },
        { label: 'Tax', align: 'r' }, '']} empty="No items yet.">
        {calc.rows.map((r, i) => (
          <tr key={i}>
            <td className="mono">{i + 1}</td>
            <td>{r.m.descr}<div className="fine mono">{r.m.code}</div></td>
            <td><input value={r.descr2 || ''} placeholder="printed after the description" maxLength={200}
              style={{ minWidth: 180 }} title="Saved on this invoice line only; the material master is unchanged"
              onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, descr2: e.target.value } : l))} /></td>
            <td className="mono">{r.m.hsn}</td>
            <td className="r"><input className="qty" type="number" min="0" value={r.qty}
              onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, qty: e.target.value } : l))} />
              {trading && Number(r.qty) > r.m.stock_qty &&
                <div className="fine" style={{ color: 'var(--red)' }}>stock {r.m.stock_qty}</div>}</td>
            <td className="c mono">{r.m.uom}</td>
            <td className="r"><input className="pr" type="number" min="0" step="0.01" value={r.price}
              onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, price: e.target.value } : l))} />
              {Math.abs(Number(r.price) - r.m.price) > 0.001 &&
                <div className="fine" style={{ color: 'var(--amber)' }}>list {inr(r.m.price)}</div>}</td>
            <td className="r mono"><b>{inr(r.amount)}</b></td>
            <td className="r mono">{r.rate}%</td>
            <td className="r mono">{inr(r.c + r.s + r.i)}</td>
            <td className="r"><button type="button" className="rm"
              onClick={() => setLines(lines.filter((_, j) => j !== i))}>×</button></td>
          </tr>))}
      </Table>
      {lines.length > 0 && <div className="panel-bd">
        <div className="totals">
          <div className="tr"><span>Taxable value</span><span>{inr(calc.taxable)}</span></div>
          {intra ? (<>
            <div className="tr"><span>CGST</span><span>{inr(calc.cgst)}</span></div>
            <div className="tr"><span>SGST</span><span>{inr(calc.sgst)}</span></div></>)
            : <div className="tr"><span>IGST</span><span>{inr(calc.igst)}</span></div>}
          <div className="tr"><span>Round off</span><span>{inr(calc.roundoff)}</span></div>
          <div className="tr grand"><span>Total</span><span>{money(calc.rounded)}</span></div>
        </div></div>}
    </Panel>

    <div className="ft">
      <button className="btn btn-a" disabled={problems.length > 0}>
        Save {h.doc_type === 'PRO' ? 'proforma' : 'invoice'}</button>
      <button type="button" className="btn" onClick={() => setLines([])}>Clear</button>
      <span className="err">{err || problems[0] || ''}</span>
    </div>
  </form>)
}
