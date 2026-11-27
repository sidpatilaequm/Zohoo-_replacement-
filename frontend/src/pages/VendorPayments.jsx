import { useState } from 'react'
import { useFyRows, FyCount } from '../lib/fy'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Alert, Tag, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

const MODES = ['NEFT', 'RTGS', 'IMPS', 'UPI', 'Cheque', 'Adjustment']

export default function VendorPayments() {
  const { api } = useAuth()
  const vinvs = useLoad(() => api.vinvs())
  const vendors = useLoad(() => api.vendors())
  const list = useLoad(() => api.vendorPayments())
  const fyRows = useFyRows()   // v5.0: the year chosen at the top
  const outstanding = useLoad(() => api.payables())
  const [payKind, setPayKind] = useState('INVOICE')
  const [f, setF] = useState({ vinv_id: '', vendor_id: '', pay_date: today(), amount: '', tds: '0', gst_tds: '',
    mode: 'NEFT', bank_ref: '', bank_acct: '', narration: '' })
  const [extraInvs, setExtraInvs] = useState({})
  const [queue, setQueue] = useState([])
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  const open = (vinvs.data || []).filter(v => v.outstanding > 0.5)
  const vi = open.find(v => v.id === Number(f.vinv_id))
  const otherVinvs = vi ? open.filter(v => v.id !== vi.id && v.vendor_id === vi.vendor_id) : []
  const extraTotal = Object.values(extraInvs).reduce((s, x) => s + (Number(x.amount) || 0), 0)
  const totalAmount = (Number(f.amount) || 0) + extraTotal

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      if (payKind === 'ADVANCE') {
        if (!f.vendor_id) throw new Error('Please select a vendor for the advance payment.')
        await api.addVendorPay({
          pay_type: 'PAY', vendor_id: Number(f.vendor_id),
          pay_date: f.pay_date, amount: Number(f.amount), tds: Number(f.tds || 0),
          gst_tds: Number(f.gst_tds || 0),
          mode: f.mode, bank_ref: f.bank_ref || null, bank_acct: f.bank_acct || null,
          narration: f.narration || 'Advance / unbilled payment'
        })
        const vendObj = vendors.data?.find(v => v.id === Number(f.vendor_id))
        showFlash(`Advance payment of ₹${inr(Number(f.amount))} recorded for ${vendObj?.name || 'vendor'}.`)
      } else {
        if (!f.vinv_id) throw new Error('Please select a vendor invoice.')
        await api.addVendorPay({ pay_type: 'PAY', vinv_id: Number(f.vinv_id),
          pay_date: f.pay_date, amount: Number(f.amount), tds: Number(f.tds || 0),
          gst_tds: Number(f.gst_tds || 0),
          mode: f.mode, bank_ref: f.bank_ref || null, bank_acct: f.bank_acct || null,
          narration: f.narration || null })
        for (const [idStr, ex] of Object.entries(extraInvs)) {
          if (Number(ex.amount) > 0) {
            await api.addVendorPay({
              pay_type: 'PAY', vinv_id: Number(idStr),
              pay_date: f.pay_date, amount: Number(ex.amount), tds: Number(ex.tds || 0),
              gst_tds: Number(ex.gst_tds || 0),
              mode: f.mode, bank_ref: f.bank_ref || null, bank_acct: f.bank_acct || null,
              narration: f.narration || null
            })
          }
        }
        const count = 1 + Object.keys(extraInvs).length
        showFlash(`Payment recorded for ${count} invoice(s) totalling ₹${inr(totalAmount)}.`)
      }
      setF(s => ({ ...s, vinv_id: '', vendor_id: '', amount: '', tds: '0', gst_tds: '', bank_ref: '', narration: '' }))
      setExtraInvs({})
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
        <div style={{ marginBottom: 14, display: 'flex', gap: 10 }}>
          <button type="button" className={`btn btn-sm ${payKind === 'INVOICE' ? 'btn-a' : ''}`}
            onClick={() => setPayKind('INVOICE')}>Against Vendor Invoice</button>
          <button type="button" className={`btn btn-sm ${payKind === 'ADVANCE' ? 'btn-a' : ''}`}
            onClick={() => { setPayKind('ADVANCE'); setExtraInvs({}) }}>Vendor Advance (Without Invoice)</button>
        </div>

        <div className="row">
          {payKind === 'ADVANCE' ? (
            <Field label="Vendor" hint="Advance / payment on account without invoice">
              <select value={f.vendor_id} onChange={e => set('vendor_id', e.target.value)} required>
                <option value="">— select vendor —</option>
                {(vendors.data || []).map(v => (
                  <option key={v.id} value={v.id}>{v.code} · {v.name}</option>
                ))}
              </select>
            </Field>
          ) : (
            <Field label="Vendor invoice"><select value={f.vinv_id}
              onChange={e => {
                set('vinv_id', e.target.value)
                setExtraInvs({})
                const v = open.find(x => x.id === Number(e.target.value))
                if (v) set('amount', v.outstanding.toFixed(2))
              }}>
              <option value="">— select —</option>
              {open.map(v => <option key={v.id} value={v.id}>
                {v.doc_no} · {v.vendor} · ₹{inr(v.outstanding)} due</option>)}
            </select></Field>
          )}
          <Field label="Payment date"><input type="date" value={f.pay_date}
            onChange={e => set('pay_date', e.target.value)} required /></Field>
          <Field label="Amount paid"><input className="mono" type="number" step="0.01"
            value={f.amount} onChange={e => set('amount', e.target.value)} required /></Field>
          <Field label="TDS withheld" hint="Deducted from the payment, still settles the invoice">
            <input className="mono" type="number" step="0.01" value={f.tds}
              onChange={e => set('tds', e.target.value)} /></Field>
          <Field label="GST withheld (GST TDS)" hint="Only if we are a GST TDS deductor · 2% of taxable">
            <input className="mono" type="number" step="0.01" min="0" value={f.gst_tds}
              onChange={e => set('gst_tds', e.target.value)} /></Field>
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

        {vi && otherVinvs.length > 0 && (
          <div style={{ marginTop: 14, marginBottom: 14, padding: '10px 14px', background: 'var(--panel-subtle, rgba(0,0,0,0.02))', borderRadius: 8, border: '1px solid var(--line2)' }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              Settle additional purchase invoices for {vi.vendor} in this payment:
            </div>
            <table style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--line2)', color: 'var(--muted)', textAlign: 'left' }}>
                  <th style={{ width: 32 }} />
                  <th>Invoice</th>
                  <th>Date</th>
                  <th style={{ textAlign: 'right' }}>Due</th>
                  <th style={{ textAlign: 'right', width: 140 }}>Amount to pay</th>
                  <th style={{ textAlign: 'right', width: 120 }}>TDS</th>
                </tr>
              </thead>
              <tbody>
                {otherVinvs.map(other => {
                  const isChecked = !!extraInvs[other.id]
                  const cur = extraInvs[other.id] || { amount: other.outstanding.toFixed(2), tds: '0', gst_tds: '0' }
                  return (
                    <tr key={other.id} style={{ borderBottom: '1px solid var(--line)' }}>
                      <td>
                        <input type="checkbox" checked={isChecked} onChange={e => {
                          if (e.target.checked) {
                            setExtraInvs({ ...extraInvs, [other.id]: { amount: other.outstanding.toFixed(2), tds: '0', gst_tds: '0' } })
                          } else {
                            const copy = { ...extraInvs }
                            delete copy[other.id]
                            setExtraInvs(copy)
                          }
                        }} />
                      </td>
                      <td className="mono"><b>{other.doc_no}</b></td>
                      <td className="mono">{gd(other.doc_date)}</td>
                      <td className="mono" style={{ textAlign: 'right' }}>₹ {inr(other.outstanding)}</td>
                      <td style={{ textAlign: 'right' }}>
                        {isChecked && (
                          <input className="mono" type="number" step="0.01" style={{ width: 120, textAlign: 'right', padding: '3px 6px' }}
                            value={cur.amount} max={other.outstanding}
                            onChange={e => setExtraInvs({ ...extraInvs, [other.id]: { ...cur, amount: e.target.value } })} />
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {isChecked && (
                          <input className="mono" type="number" step="0.01" style={{ width: 100, textAlign: 'right', padding: '3px 6px' }}
                            value={cur.tds}
                            onChange={e => setExtraInvs({ ...extraInvs, [other.id]: { ...cur, tds: e.target.value } })} />
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {Object.keys(extraInvs).length > 0 && (
              <div style={{ marginTop: 8, fontSize: 12.5, textAlign: 'right', fontWeight: 600 }}>
                Total payment across {1 + Object.keys(extraInvs).length} invoices: ₹ {inr(totalAmount)}
              </div>
            )}
          </div>
        )}

        <div className="ft">
          <button className="btn btn-a" disabled={!f.vinv_id || !Number(f.amount)}>
            Record payment {Object.keys(extraInvs).length > 0 ? `(₹ ${inr(totalAmount)})` : ''}
          </button>
          <button type="button" className="btn" onClick={() => {
            if (!vi) return setErr('Select a vendor invoice.')
            const allDocs = [vi.doc_no, ...Object.keys(extraInvs).map(id => open.find(v => v.id === Number(id))?.doc_no)].filter(Boolean)
            setQueue([...queue, { party: vi.vendor, doc: allDocs.join(', '),
              amount: totalAmount, mode: f.mode }])
            showFlash(`Queued. ${queue.length + 1} item(s) in the bank file.`)
          }}>Add to bank file</button>
          <span className="err">{err}</span></div>
      </Panel>
    </form>

    <Panel title={<>Payments — <FyCount shown={fyRows(list.data).length} total={(list.data || []).length} /></>} right={
      <button className="btn btn-sm" onClick={downloadBankFile}>Download bank upload file</button>}
      bodyless>
      <Table head={['Date', 'Vendor', 'Against', { label: 'Mode', align: 'c' }, 'Reference',
        { label: 'TDS', align: 'r' }, { label: 'GST withheld', align: 'r' }, { label: 'Amount', align: 'r' }, '']}
        empty="No payments recorded.">
        {fyRows(list.data).map(p => (
          <tr key={p.id}>
            <td className="mono">{gd(p.pay_date)}</td><td>{p.party}</td>
            <td className="mono">{p.doc === 'Advance / On Account' ? <Tag kind="ok">Advance / On Account</Tag> : p.doc}</td><td className="c">{p.mode}</td>
            <td className="mono fine">{p.bank_ref || '—'}</td>
            <td className="r mono">{p.tds ? inr(p.tds) : '—'}</td>
            <td className="r mono">{p.gst_tds ? inr(p.gst_tds) : '—'}</td>
            <td className="r mono"><b>{inr(p.amount)}</b></td>
            <td className="r">{p.from_bank
              ? <span title="Posted from Bank Statements. Remove the attachment on Bank Statements to undo it."><Tag>bank</Tag></span>
              : <button className="rm" onClick={async () => {
              try { await api.delPayment(p.id); list.reload(); vinvs.reload(); outstanding.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>×</button>}</td>
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
