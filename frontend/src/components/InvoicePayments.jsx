import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Alert, Field, Loading, useLoad } from './ui'
import { inr, gd } from '../lib/fmt'

const r2 = n => Math.round(n * 100) / 100
const TDS_RATES = [0.01, 0.02, 0.1]

/** v5.0 — an invoice's payments, in one place.
 *
 *  Every payment against the invoice — from the bank statement or entered by
 *  hand — with the TDS and GST withheld on each, and what is still open. For
 *  someone who works Bank Statements, the bank lines that could still settle
 *  it are listed: tick one or several and attach them together. When they do
 *  not add up to what is open, the shortfall can be marked as TDS and GST
 *  withheld (it goes on the last line) or left open.
 *
 *  linkType: CUST_INV | VEND_INV. */
export default function InvoicePayments({ linkType, id, onClose, onChanged }) {
  const { api } = useAuth()
  const d = useLoad(() => api.invoicePayments(linkType, id), [linkType, id])
  const [pick, setPick] = useState({})          // txn_id -> amount (string)
  const [withhold, setWithhold] = useState(true)
  const [tds, setTds] = useState('')
  const [gst, setGst] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')
  const [changed, setChanged] = useState(false)
  // The register behind is refreshed when the window closes: refreshing it now
  // would redraw the page and lose this window.
  const close = () => { if (changed && onChanged) onChanged(); onClose() }
  const D = d.data
  const credit = linkType === 'CUST_INV'

  useEffect(() => { setPick({}); setTds(''); setGst('') }, [D])

  const chosen = useMemo(() => Object.entries(pick).map(([k, v]) => ({ txn_id: Number(k), amount: Number(v) || 0 })), [pick])
  const money = r2(chosen.reduce((s, x) => s + x.amount, 0))
  const short = D ? r2(D.open - money) : 0
  const w = withhold ? (Number(tds) || 0) + (Number(gst) || 0) : 0
  const after = r2(short - w)

  function toggle(c) {
    setPick(p => {
      const n = { ...p }
      if (n[c.txn_id] !== undefined) { delete n[c.txn_id]; return n }
      const used = Object.values(n).reduce((s, v) => s + (Number(v) || 0), 0)
      const room = r2(Math.max(D.open - used, 0))
      n[c.txn_id] = String(Math.min(c.remaining, room || c.remaining).toFixed(2))
      return n
    })
  }

  async function save() {
    setBusy(true); setErr('')
    try {
      const r = await api.matchInvoicePayments({
        link_type: linkType, ref_id: id, notes: notes || null,
        items: chosen.map(c => ({ txn_id: c.txn_id, amount: c.amount || null })),
        tds: withhold && short > 0.005 && Number(tds) > 0 ? Number(tds) : null,
        gst_tds: withhold && short > 0.005 && Number(gst) > 0 ? Number(gst) : null,
      })
      setDone(`${chosen.length} bank line(s) attached.${r.open > 0.005 ? ` ${inr(r.open)} is still open.` : ' The invoice is settled.'}`)
      d.reload(); setChanged(true)
    } catch (x) { setErr(x.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget && !busy) close() }}>
      <div className="modal tx wide" role="dialog" aria-modal="true" aria-labelledby="ip-title">
        <div className="modal-hd"><h2 id="ip-title">Payments{D && <span className="fine">{D.doc_no} · {D.party}</span>}</h2>
          <button type="button" className="rm" onClick={close} title="Close">×</button></div>
        <div className="modal-bd">
          {d.loading && !D ? <Loading /> : d.error ? <Alert kind="bad">{d.error}</Alert> : <>
            <div className="inv-sum">
              <span><span className="k">Invoice</span><b>{inr(D.total)}</b></span>
              <span><span className="k">Taxable</span><b>{inr(D.taxable)}</b></span>
              <span><span className="k">GST</span><b>{inr(D.gst)}</b></span>
              <span><span className="k">{credit ? 'Received' : 'Paid'}</span><b>{inr(D.paid)}</b></span>
              <span><span className="k">TDS deducted</span><b>{inr(D.tds)}</b></span>
              <span><span className="k">GST withheld</span><b>{inr(D.gst_tds)}</b></span>
              <span><span className="k">Open</span><b>{inr(D.open)}</b></span>
            </div>
            {done && <Alert kind="ok">{done}</Alert>}

            <h3 style={{ margin: '12px 0 4px', fontSize: 14 }}>Payments against this invoice</h3>
            {D.payments.length
              ? <table className="paylist"><thead><tr><th>Date</th><th>From</th><th>Reference</th>
                  <th className="r">Amount</th><th className="r">TDS</th><th className="r">GST withheld</th></tr></thead>
                <tbody>{D.payments.map((p, i) => <tr key={i}>
                  <td className="mono">{gd(p.date)}</td><td className="fine">{p.source}</td>
                  <td className="fine mono">{p.ref}</td><td className="r">{inr(p.amount)}</td>
                  <td className="r">{p.tds ? inr(p.tds) : '—'}</td><td className="r">{p.gst_tds ? inr(p.gst_tds) : '—'}</td></tr>)}
                  <tr><td colSpan={3}><b>Total</b></td><td className="r"><b>{inr(D.paid)}</b></td>
                    <td className="r"><b>{inr(D.tds)}</b></td><td className="r"><b>{inr(D.gst_tds)}</b></td></tr></tbody></table>
              : <div className="fine">Nothing received or paid against it yet.</div>}

            {D.open > 0.005 && D.can_attach && <>
              <h3 style={{ margin: '14px 0 4px', fontSize: 14 }}>Bank lines that could settle it</h3>
              {!D.candidates.length
                ? <div className="fine">No {credit ? 'credit' : 'debit'} with money left to attach, from 90 days before the
                    invoice on. Upload the statement on Bank Statements first.</div>
                : <table className="paylist"><thead><tr><th /><th>Date</th><th>Account</th><th>Narration</th>
                    <th className="r">Left to attach</th><th className="r">Attach</th></tr></thead>
                  <tbody>{D.candidates.map(c => {
                    const on = pick[c.txn_id] !== undefined
                    return <tr key={c.txn_id}>
                      <td><input type="checkbox" checked={on} onChange={() => toggle(c)} aria-label={`Attach ${c.descr}`} /></td>
                      <td className="mono">{gd(c.date)}</td><td className="fine">{c.account}</td>
                      <td className="fine">{c.exact && <b>✓ exact · </b>}{c.descr}</td>
                      <td className="r">{inr(c.remaining)}</td>
                      <td className="r">{on && <input className="mono" style={{ width: 100 }} type="number" step="0.01" min="0.01"
                        max={c.remaining} value={pick[c.txn_id]} onChange={e => setPick({ ...pick, [c.txn_id]: e.target.value })} />}</td>
                    </tr>})}</tbody></table>}

              {chosen.length > 0 && <>
                {short > 0.005
                  ? <div className={`short${after < -0.005 ? ' bad' : withhold && Math.abs(after) <= 0.005 ? ' ok' : ''}`}>
                      <div><b>Does not tally: {inr(short)} short</b> — {inr(money)} from {chosen.length} line(s) against {inr(D.open)} open.</div>
                      <div className="row" style={{ marginTop: 6 }}>
                        <Field label="The shortfall is">
                          <select value={withhold ? 'W' : 'O'} onChange={e => setWithhold(e.target.value === 'W')}>
                            <option value="W">Withheld by {credit ? 'the customer' : 'us'} — TDS / GST</option>
                            <option value="O">Still to come — leave it open</option></select></Field>
                        {withhold && <>
                          <Field label="TDS withheld">
                            <input className="mono" type="number" step="0.01" min="0" value={tds} onChange={e => setTds(e.target.value)} />
                            <span className="qf">{TDS_RATES.map(rt => <button type="button" key={rt}
                              onClick={() => setTds(r2(D.taxable * rt).toFixed(2))}>{rt * 100}%</button>)}
                              <button type="button" onClick={() => setTds(r2(short - (Number(gst) || 0)).toFixed(2))}>rest</button></span></Field>
                          <Field label="GST withheld (GST TDS)">
                            <input className="mono" type="number" step="0.01" min="0" value={gst} onChange={e => setGst(e.target.value)} />
                            <span className="qf"><button type="button" onClick={() => setGst(r2(D.taxable * 0.02).toFixed(2))}>2%</button>
                              <button type="button" onClick={() => setGst(r2(short - (Number(tds) || 0)).toFixed(2))}>rest</button></span></Field>
                          <Field label="Still open after this">
                            <div className="mono" style={{ paddingTop: 8 }}><b>{inr(Math.max(after, 0))}</b>{after < -0.005 && ' — more than the shortfall'}</div></Field>
                        </>}
                      </div>
                    </div>
                  : short < -0.005
                    ? <Alert kind="bad">The lines come to {inr(money)}, more than the {inr(D.open)} open. Lower an amount.</Alert>
                    : <Alert kind="ok">The lines settle the invoice exactly.</Alert>}
                <div className="ft">
                  <input placeholder="Note (optional)" maxLength={200} value={notes} onChange={e => setNotes(e.target.value)} style={{ flex: 1 }} />
                  <button type="button" className="btn btn-a" onClick={save}
                    disabled={busy || short < -0.005 || (withhold && after < -0.005) || chosen.some(c => c.amount <= 0)}>
                    {busy ? 'Attaching…' : `Attach ${chosen.length} line${chosen.length > 1 ? 's' : ''}`}</button>
                  {err && <span className="err">{err}</span>}
                </div>
              </>}
            </>}
            {D.open > 0.005 && !D.can_attach && <div className="fine" style={{ marginTop: 10 }}>Bank lines are attached on Bank
              Statements, by someone with access to it.</div>}
          </>}
        </div>
      </div>
    </div>)
}
