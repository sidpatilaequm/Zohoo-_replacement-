import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash,
  usePrintVariant, VariantPicker, PrintButtons } from '../components/ui'
import { inr, money, gd, today } from '../lib/fmt'

const MODES = ['NEFT', 'RTGS', 'IMPS', 'UPI', 'Cheque', 'Cash', 'Adjustment']

export default function Receipts() {
  const { api } = useAuth()
  const invoices = useLoad(() => api.invoices())
  const list = useLoad(() => api.receipts())
  const outstanding = useLoad(() => api.receivables())
  const [f, setF] = useState({ invoice_id: '', pay_date: today(), amount: '',
    mode: 'NEFT', bank_ref: '', bank_acct: '', narration: '' })
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const [variant, setVariant] = usePrintVariant()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  const open = (invoices.data || []).filter(v => v.doc_type === 'TAX' && v.outstanding > 0.5)
  const inv = open.find(v => v.id === Number(f.invoice_id))

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      await api.addReceipt({ pay_type: 'REC', invoice_id: Number(f.invoice_id),
        pay_date: f.pay_date, amount: Number(f.amount), tds: 0, mode: f.mode,
        bank_ref: f.bank_ref || null, bank_acct: f.bank_acct || null,
        narration: f.narration || null })
      showFlash('Receipt recorded.')
      setF(s => ({ ...s, invoice_id: '', amount: '', bank_ref: '', narration: '' }))
      list.reload(); invoices.reload(); outstanding.reload()
    } catch (x) { setErr(x.message) }
  }
  if (invoices.loading || list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <Alert kind="ok"><b>Manual financial entry.</b> Receipts are keyed in from your bank statement
      or pay-in slip. There is no bank integration and none is needed — nothing is fetched or
      transmitted, so the register only ever contains what someone has confirmed happened.</Alert>

    <form onSubmit={save}>
      <Panel title="Record a receipt from a customer">
        <div className="row">
          <Field label="Invoice"><select value={f.invoice_id}
            onChange={e => { set('invoice_id', e.target.value)
              const v = open.find(x => x.id === Number(e.target.value))
              if (v) set('amount', v.outstanding.toFixed(2)) }}>
            <option value="">— select an invoice —</option>
            {open.map(v => <option key={v.id} value={v.id}>
              {v.doc_no} · {v.customer} · ₹{inr(v.outstanding)} due</option>)}
          </select></Field>
          <Field label="Date received"><input type="date" value={f.pay_date}
            onChange={e => set('pay_date', e.target.value)} required /></Field>
          <Field label="Amount"><input className="mono" type="number" step="0.01"
            value={f.amount} onChange={e => set('amount', e.target.value)} required /></Field>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <Field label="Mode"><select value={f.mode} onChange={e => set('mode', e.target.value)}>
            {MODES.map(m => <option key={m}>{m}</option>)}</select></Field>
          <Field label="Bank or instrument reference"><input className="mono" value={f.bank_ref}
            placeholder="UTR, cheque no or slip no"
            onChange={e => set('bank_ref', e.target.value)} /></Field>
          <Field label="Bank account credited"><input value={f.bank_acct}
            onChange={e => set('bank_acct', e.target.value)} /></Field>
          <Field label="Narration"><input value={f.narration}
            onChange={e => set('narration', e.target.value)} /></Field>
        </div>
        {inv && <Alert kind="ok">Invoice total {money(inv.total)}, received so far{' '}
          {money(inv.received)}, <b>outstanding {money(inv.outstanding)}</b>.</Alert>}
        <div className="ft"><button className="btn btn-a"
          disabled={!f.invoice_id || !Number(f.amount)}>Record receipt</button>
          <span className="err">{err}</span></div>
      </Panel>
    </form>

    <Panel title={`Receipts — ${list.data.length}`}
      right={<VariantPicker value={variant} onChange={setVariant} />} bodyless>
      <Table head={['Date', 'Customer', 'Against', { label: 'Mode', align: 'c' },
        'Reference', 'Bank', { label: 'Amount', align: 'r' },
        { label: 'Receipt voucher', align: 'c' }, '']} empty="No receipts recorded.">
        {list.data.map(p => (
          <tr key={p.id} style={p.reverses_id ? { background: 'var(--red-soft)' } : undefined}>
            <td className="mono">{gd(p.pay_date)}</td><td>{p.party}
              {p.reverses_id && <div className="fine">{p.narration}</div>}</td>
            <td className="mono">{p.doc}</td><td className="c">{p.reverses_id
              ? <Tag kind="bad">Reversal</Tag> : p.mode}</td>
            <td className="mono fine">{p.bank_ref || '—'}</td>
            <td className="fine">{p.bank_acct || '—'}</td>
            <td className="r mono"><b>{inr(p.amount)}</b></td>
            <td className="c">{!p.reverses_id && <PrintButtons kind="receipts" id={p.id} variant={variant}
              onError={m => showFlash(m, 'bad')} />}</td>
            <td className="r"><button className="rm" onClick={async () => {
              try { await api.delPayment(p.id); list.reload(); invoices.reload(); outstanding.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>×</button></td>
          </tr>))}
      </Table>
    </Panel>

    <Panel title="Outstanding from customers" bodyless>
      <Table head={['Customer', 'Invoice', 'Date', 'Due', { label: 'Total', align: 'r' },
        { label: 'Received', align: 'r' }, { label: 'Outstanding', align: 'r' }]}
        empty="Nothing outstanding.">
        {(outstanding.data || []).map(r => (
          <tr key={r.doc_no}>
            <td>{r.customer}</td><td className="mono">{r.doc_no}</td>
            <td className="mono">{gd(r.doc_date)}</td><td className="mono">{gd(r.due_date)}</td>
            <td className="r mono">{inr(r.total)}</td><td className="r mono">{inr(r.received)}</td>
            <td className="r mono"><b>{inr(r.outstanding)}</b></td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
