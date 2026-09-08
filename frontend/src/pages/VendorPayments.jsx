import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

const MODES = ['NEFT', 'RTGS', 'IMPS', 'UPI', 'Cheque', 'Adjustment']

export default function VendorPayments() {
  const { api } = useAuth()
  const vinvs = useLoad(() => api.vinvs())
  const list = useLoad(() => api.vendorPayments())
  const outstanding = useLoad(() => api.payables())
  const [f, setF] = useState({ vinv_id: '', pay_date: today(), amount: '', tds: '0',
    mode: 'NEFT', bank_ref: '', bank_acct: '', narration: '' })
  const [queue, setQueue] = useState([])
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  const open = (vinvs.data || []).filter(v => v.outstanding > 0.5)
  const vi = open.find(v => v.id === Number(f.vinv_id))

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      await api.addVendorPay({ pay_type: 'PAY', vinv_id: Number(f.vinv_id),
        pay_date: f.pay_date, amount: Number(f.amount), tds: Number(f.tds || 0),
        mode: f.mode, bank_ref: f.bank_ref || null, bank_acct: f.bank_acct || null,
        narration: f.narration || null })
      showFlash('Payment recorded.')
      setF(s => ({ ...s, vinv_id: '', amount: '', tds: '0', bank_ref: '', narration: '' }))
      list.reload(); vinvs.reload(); outstanding.reload()
    } catch (x) { setErr(x.message) }
  }
  function downloadBankFile() {
    const rows = queue.length ? queue
      : (list.data || []).map(p => ({ party: p.party, doc: p.doc, amount: p.amount, mode: p.mode }))
    if (!rows.length) return showFlash('Nothing queued and no payments recorded.', 'bad')
    const csv = [['Beneficiary Name', 'Beneficiary Account', 'IFSC', 'Amount', 'Mode',
      'Remarks', 'Debit Account'].join(','),
      ...rows.map(r => [r.party, '', '', Number(r.amount).toFixed(2), r.mode,
        'Against ' + r.doc, ''].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'bank_upload.csv'; a.click()
    URL.revokeObjectURL(url)
    showFlash('Beneficiary account numbers and IFSC codes are blank — fill them in before uploading.', 'bad')
  }
  if (vinvs.loading || list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <Alert kind="ok"><b>Manual financial entry.</b> Payments are recorded after they have been made
      through your bank. Nothing here initiates a transfer — the bank file is a list you upload to
      your bank's own bulk-transfer facility, and release stays with your signatories.</Alert>

    <form onSubmit={save}>
      <Panel title="Record a payment to a vendor">
        <div className="row">
          <Field label="Vendor invoice"><select value={f.vinv_id}
            onChange={e => { set('vinv_id', e.target.value)
              const v = open.find(x => x.id === Number(e.target.value))
              if (v) set('amount', v.outstanding.toFixed(2)) }}>
            <option value="">— select —</option>
            {open.map(v => <option key={v.id} value={v.id}>
              {v.doc_no} · {v.vendor} · ₹{inr(v.outstanding)} due</option>)}
          </select></Field>
          <Field label="Payment date"><input type="date" value={f.pay_date}
            onChange={e => set('pay_date', e.target.value)} required /></Field>
          <Field label="Amount paid"><input className="mono" type="number" step="0.01"
            value={f.amount} onChange={e => set('amount', e.target.value)} required /></Field>
          <Field label="TDS withheld" hint="Deducted from the payment, still settles the invoice">
            <input className="mono" type="number" step="0.01" value={f.tds}
              onChange={e => set('tds', e.target.value)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <Field label="Mode"><select value={f.mode} onChange={e => set('mode', e.target.value)}>
            {MODES.map(m => <option key={m}>{m}</option>)}</select></Field>
          <Field label="Bank or instrument reference"><input className="mono" value={f.bank_ref}
            onChange={e => set('bank_ref', e.target.value)} /></Field>
          <Field label="Bank account debited"><input value={f.bank_acct}
            onChange={e => set('bank_acct', e.target.value)} /></Field>
          <Field label="Narration"><input value={f.narration}
            onChange={e => set('narration', e.target.value)} /></Field>
        </div>
        {vi && <Alert kind="ok">Invoice total {money(vi.total)}, paid so far {money(vi.paid)},{' '}
          <b>outstanding {money(vi.outstanding)}</b>.</Alert>}
        <div className="ft">
          <button className="btn btn-a" disabled={!f.vinv_id || !Number(f.amount)}>Record payment</button>
          <button type="button" className="btn" onClick={() => {
            if (!vi) return setErr('Select a vendor invoice.')
            setQueue([...queue, { party: vi.vendor, doc: vi.doc_no,
              amount: Number(f.amount), mode: f.mode }])
            showFlash(`Queued. ${queue.length + 1} item(s) in the bank file.`)
          }}>Add to bank file</button>
          <span className="err">{err}</span></div>
      </Panel>
    </form>

    <Panel title={`Payments — ${list.data.length}`} right={
      <button className="btn btn-sm" onClick={downloadBankFile}>Download bank upload file</button>}
      bodyless>
      <Table head={['Date', 'Vendor', 'Against', { label: 'Mode', align: 'c' }, 'Reference',
        { label: 'TDS', align: 'r' }, { label: 'Amount', align: 'r' }, '']}
        empty="No payments recorded.">
        {list.data.map(p => (
          <tr key={p.id}>
            <td className="mono">{gd(p.pay_date)}</td><td>{p.party}</td>
            <td className="mono">{p.doc}</td><td className="c">{p.mode}</td>
            <td className="mono fine">{p.bank_ref || '—'}</td>
            <td className="r mono">{p.tds ? inr(p.tds) : '—'}</td>
            <td className="r mono"><b>{inr(p.amount)}</b></td>
            <td className="r"><button className="rm" onClick={async () => {
              try { await api.delPayment(p.id); list.reload(); vinvs.reload(); outstanding.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>×</button></td>
          </tr>))}
      </Table>
    </Panel>

    <Panel title="Outstanding to vendors" bodyless>
      <Table head={['Vendor', 'Invoice', 'Date', 'Due', { label: 'Total', align: 'r' },
        { label: 'Paid', align: 'r' }, { label: 'Outstanding', align: 'r' }]}
        empty="Nothing outstanding.">
        {(outstanding.data || []).map(r => (
          <tr key={r.doc_no}>
            <td>{r.vendor}</td><td className="mono">{r.doc_no}</td>
            <td className="mono">{gd(r.doc_date)}</td><td className="mono">{gd(r.due_date)}</td>
            <td className="r mono">{inr(r.total)}</td><td className="r mono">{inr(r.paid)}</td>
            <td className="r mono"><b>{inr(r.outstanding)}</b></td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
