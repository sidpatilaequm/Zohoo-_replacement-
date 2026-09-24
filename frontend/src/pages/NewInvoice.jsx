import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, today } from '../lib/fmt'

export default function NewInvoice() {
  const { api, me } = useAuth()
  const customers = useLoad(() => api.customers())
  const materials = useLoad(() => api.materials())
  const states = useLoad(() => api.states())
  const hsn = useLoad(() => api.hsn())
  const [h, setH] = useState({ doc_type: 'TAX', doc_date: today(), due_date: '',
    customer_id: '', gstin: '', pos_state: '', bill_addr_id: '', ship_addr_id: '',
    po_no: '', po_date: '', reverse_chg: 'N', price_mode: 'MATERIAL',
    subject: '', instructions: '' })
  const trading = me?.tenant?.company_type === 'TRADING'
  const [lines, setLines] = useState([])
  const [pick, setPick] = useState('')
  const [addrs, setAddrs] = useState([])
  const [rateMap, setRateMap] = useState({})   // hsn code -> permitted rates
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setH(s => ({ ...s, [k]: v }))

  const cust = customers.data?.find(c => c.id === Number(h.customer_id))
  const regs = cust?.gstins || []
  const reg = regs.find(r => r.gstin === h.gstin) || regs.find(r => r.is_default) || regs[0]
  const billAddr = addrs.find(a => String(a.id) === String(h.bill_addr_id))
  const shipAddr = addrs.find(a => String(a.id) === String(h.ship_addr_id))

  // Where the place of supply would land if nobody touched it
  const defaultPos = billAddr?.state_code || reg?.state_code || cust?.bill_state
  const pos = h.pos_state || defaultPos
  const posOverridden = !!h.pos_state && h.pos_state !== defaultPos
  const orgState = me?.tenant?.state_code
  const intra = pos === orgState

  // A customer can hold several addresses; load them when one is chosen
  useEffect(() => {
    let alive = true
    if (!h.customer_id) { setAddrs([]); return }
    api.addresses('customer', Number(h.customer_id))
      .then(r => { if (alive) setAddrs(r) })
      .catch(() => { if (alive) setAddrs([]) })
    return () => { alive = false }
  }, [h.customer_id, api])

  // Due date follows the payment terms on the customer, until it is typed over
  useEffect(() => {
    if (!cust || !h.doc_date) return
    const days = Number(cust.payment_term_days || 0)
    if (!days) return
    const d = new Date(h.doc_date)
    d.setDate(d.getDate() + days)
    const iso = d.toISOString().slice(0, 10)
    setH(s => (s.due_date && s.due_touched) ? s : { ...s, due_date: iso })
    // eslint-disable-next-line
  }, [h.customer_id, h.doc_date, cust && cust.payment_term_days])

  // The permitted rates for each code used on this invoice
  useEffect(() => {
    const codes = (hsn.data || []).filter(x => lines.some(l => {
      const m = materials.data?.find(z => z.id === l.material_id); return m && m.hsn === x.code }))
    let alive = true
    Promise.all(codes.map(x => api.hsnRates(x.id).then(r => [x.code, r]).catch(() => [x.code, []])))
      .then(pairs => { if (alive) setRateMap(Object.fromEntries(pairs)) })
    return () => { alive = false }
    // eslint-disable-next-line
  }, [lines.length, hsn.data])

  const calc = useMemo(() => {
    let taxable = 0, cgst = 0, sgst = 0, igst = 0
    const rows = lines.map(l => {
      const m = materials.data?.find(x => x.id === l.material_id)
      if (!m) return null
      const gross = Math.round(Number(l.qty) * Number(l.price) * 100) / 100
      // A picked rate wins over the material default; the head still follows
      // the place of supply, which is not the user's to choose.
      const chosen = (rateMap[m.hsn] || []).find(x => String(x.id) === String(l.hsn_rate_id))
      const pcgst = chosen ? chosen.cgst_pct : m.cgst_pct
      const psgst = chosen ? chosen.sgst_pct : m.sgst_pct
      const pigst = chosen ? chosen.igst_pct : m.igst_pct
      const rate = intra ? pcgst + psgst : pigst
      const incl = h.price_mode === 'INCL' ? true
        : h.price_mode === 'EXCL' ? false : !!m.price_inclusive
      let amount, c, s, i
      if (incl) {
        // carve the tax out, by subtraction, so the parts add back to the gross
        amount = rate ? Math.round(gross * 100 / (100 + rate) * 100) / 100 : gross
        const carved = Math.round((gross - amount) * 100) / 100
        if (intra) {
          c = (pcgst + psgst) ? Math.round(carved * pcgst / (pcgst + psgst) * 100) / 100 : 0
          s = Math.round((carved - c) * 100) / 100
          i = 0
        } else { c = 0; s = 0; i = carved }
      } else {
        amount = gross
        c = intra ? Math.round(amount * pcgst) / 100 : 0
        s = intra ? Math.round(amount * psgst) / 100 : 0
        i = intra ? 0 : Math.round(amount * pigst) / 100
      }
      taxable += amount; cgst += c; sgst += s; igst += i
      return { ...l, m, amount, gross, c, s, i, chosen, incl, rate }
    }).filter(Boolean)
    const total = taxable + cgst + sgst + igst
    const rounded = Math.round(total)
    return { rows, taxable, cgst, sgst, igst, total, rounded, roundoff: rounded - total }
  }, [lines, materials.data, intra, rateMap, h.price_mode])

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
        price_mode: h.price_mode,
        bill_addr_id: h.bill_addr_id ? Number(h.bill_addr_id) : null,
        ship_addr_id: h.ship_addr_id ? Number(h.ship_addr_id) : null,
        subject: h.subject || null, instructions: h.instructions || null,
        lines: lines.map(l => ({ material_id: l.material_id, qty: Number(l.qty),
          price: Number(l.price), descr2: l.descr2 || null,
          hsn_rate_id: l.hsn_rate_id ? Number(l.hsn_rate_id) : null })) })
      showFlash(`${h.doc_type === 'PRO' ? 'Proforma' : 'Invoice'} ${d.doc_no} saved — ${money(d.totals.rounded)}.`)
      setLines([]); setH(s => ({ ...s, customer_id: '', gstin: '', pos_state: '', bill_addr_id: '',
        ship_addr_id: '', po_no: '', po_date: '', subject: '', instructions: '',
        due_touched: false }))
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
        <Field label="Bill to address"
          hint={addrs.length ? `${addrs.length} on file` : 'The one on the customer record'}>
          <select value={h.bill_addr_id} disabled={!addrs.length}
            onChange={e => { set('bill_addr_id', e.target.value); set('pos_state', '') }}>
            <option value="">Address on the customer record</option>
            {addrs.filter(a => a.addr_type !== 'SHIPPING').map(a => (
              <option key={a.id} value={a.id}>{a.label} — {a.city} ({a.state_code})</option>))}
          </select></Field>
        <Field label="Ship to address" hint="Left blank, delivery follows billing">
          <select value={h.ship_addr_id} disabled={!addrs.length}
            onChange={e => set('ship_addr_id', e.target.value)}>
            <option value="">Same as billing</option>
            {addrs.filter(a => a.addr_type !== 'BILLING').map(a => (
              <option key={a.id} value={a.id}>{a.label} — {a.city} ({a.state_code})</option>))}
          </select></Field>
        <Field label="Invoice date"><input type="date" value={h.doc_date}
          onChange={e => set('doc_date', e.target.value)} required /></Field>
        <Field label="Due date"
          hint={cust && cust.payment_term_days
            ? `Invoice date plus ${cust.payment_term_days} days from the customer master`
            : 'No payment terms on this customer'}>
          <input type="date" value={h.due_date}
            onChange={e => setH(s => ({ ...s, due_date: e.target.value,
              due_touched: true }))} /></Field>
      </div>
      <div className="row" style={{ marginTop: 13 }}>
        <Field label="PO number"><input className="mono" value={h.po_no}
          onChange={e => set('po_no', e.target.value)} /></Field>
        <Field label="PO date"><input type="date" value={h.po_date}
          onChange={e => set('po_date', e.target.value)} /></Field>
        <Field label="Place of supply"
          hint={posOverridden
            ? 'Overridden by hand — it no longer follows the billing address'
            : 'Defaults from the billing address, and can be changed'}>
          <select value={pos || ''}
            style={posOverridden ? { borderColor: 'var(--amber)',
              background: 'var(--amber-soft)' } : undefined}
            onChange={e => set('pos_state', e.target.value)}>
            {states.data.map(s => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
          </select>
          {posOverridden && <button type="button" className="btn btn-sm"
            style={{ marginTop: 6 }} onClick={() => set('pos_state', '')}>
            Put it back to {defaultPos}</button>}</Field>
        <Field label="Prices on this invoice are"
          hint={h.price_mode === 'MATERIAL'
            ? 'Each line follows the basis on its material'
            : h.price_mode === 'INCL'
              ? 'Every line treated as having GST already in the price'
              : 'GST added on top of every line'}>
          <select value={h.price_mode}
            style={h.price_mode !== 'MATERIAL'
              ? { borderColor: 'var(--amber)', background: 'var(--amber-soft)' }
              : undefined}
            onChange={e => set('price_mode', e.target.value)}>
            <option value="MATERIAL">As set on each material</option>
            <option value="EXCL">All exclusive of GST</option>
            <option value="INCL">All inclusive of GST</option>
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
        {billAddr && <>Billed to <b>{billAddr.label}</b>
          {billAddr.gstin ? ` under ${billAddr.gstin}` : ''}<br /></>}
        Place of supply {pos} — {stateName(pos)}
        {posOverridden ? ' (set by hand)' : ''}. {intra
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
        { label: 'Amount', align: 'r' }, { label: 'Basis', align: 'c' },
        'GST rate', { label: 'Tax %', align: 'r' },
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
            <td className="c">{r.incl
              ? <><Tag kind="warn">incl</Tag>
                  <div className="fine">of {inr(r.gross)}</div></>
              : <Tag kind="ok">excl</Tag>}</td>
            <td>{(rateMap[r.m.hsn] || []).length > 1
              ? <select value={r.hsn_rate_id || ''} style={{ padding: '5px 7px',
                  border: '1px solid var(--line2)', borderRadius: 6, maxWidth: 150 }}
                  onChange={e => setLines(lines.map((l, j) =>
                    j === i ? { ...l, hsn_rate_id: e.target.value } : l))}>
                  <option value="">Material default ({r.m.igst_pct}%)</option>
                  {(rateMap[r.m.hsn] || []).map(x => (
                    <option key={x.id} value={x.id}>{x.label} ({x.igst_pct}%)</option>))}
                </select>
              : <span className="fine">{(rateMap[r.m.hsn] || []).length === 1
                  ? (rateMap[r.m.hsn][0].label) : 'single rate'}</span>}
              {r.chosen && r.chosen.condition_note &&
                <div className="fine">{r.chosen.condition_note}</div>}</td>
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
        </div>
        {calc.rows.some(r => r.incl) && (() => {
          const quoted = calc.rows.reduce((a, r) => a + (r.incl ? r.gross : r.gross ??
            (r.amount + r.c + r.s + r.i)), 0)
          return <Alert kind="ok">
            <b>Some lines were quoted inclusive of GST.</b> The tax on those has been carved
            out of the quoted figure rather than added to it, so the customer pays exactly
            what they were quoted. Sum of the quoted line figures: {money(quoted)}.
          </Alert>
        })()}
        </div>}
    </Panel>

    <div className="ft">
      <button className="btn btn-a" disabled={problems.length > 0}>
        Save {h.doc_type === 'PRO' ? 'proforma' : 'invoice'}</button>
      <button type="button" className="btn" onClick={() => setLines([])}>Clear</button>
      <span className="err">{err || problems[0] || ''}</span>
    </div>
  </form>)
}
