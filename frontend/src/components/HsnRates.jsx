import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert } from './ui'

const BLANK = { label: '', sgst_pct: '9', cgst_pct: '9', igst_pct: '18',
  cess_pct: '0', condition_note: '', is_default: false }

/**
 * The permitted rates against one code.
 *
 * A rate is not a property of the code. It comes from the rate notification
 * entry, and one code can sit against more than one entry — the same SAC can
 * carry a concessional rate on condition credit is not taken and a standard
 * rate with credit. So the code holds a list, and the invoice line says which
 * one applies.
 */
export default function HsnRates({ hsn }) {
  const { api } = useAuth()
  const [rows, setRows] = useState([])
  const [f, setF] = useState(BLANK)
  const [err, setErr] = useState(null)
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))
  const split = Number(f.sgst_pct) + Number(f.cgst_pct)
  const mismatch = Math.abs(split - Number(f.igst_pct)) > 0.005

  async function load() {
    try { setRows(await api.hsnRates(hsn.id)) } catch (x) { setErr(x.message) }
  }
  useEffect(() => { load() /* eslint-disable-next-line */ }, [hsn.id])

  async function add() {
    setErr(null)
    try {
      await api.addHsnRate(hsn.id, { ...f,
        sgst_pct: Number(f.sgst_pct), cgst_pct: Number(f.cgst_pct),
        igst_pct: Number(f.igst_pct), cess_pct: Number(f.cess_pct || 0),
        condition_note: f.condition_note.trim() || null })
      setF(BLANK); load()
    } catch (x) { setErr(x.message) }
  }

  return (
    <Panel title={`Permitted rates on ${hsn.code} — ${rows.length}`}>
      <Alert kind="ok">A code can carry more than one rate. The rate comes from the
        notification entry, not from the code, and one code can sit against several entries.
        Add each permitted rate here with the condition that earns it, and the person raising
        the invoice picks which applies. <b>Picking the rate does not pick the head</b> —
        whether it lands as CGST and SGST or as IGST still follows the place of supply.</Alert>

      <Table head={['Rate', { label: 'SGST', align: 'r' }, { label: 'CGST', align: 'r' },
        { label: 'IGST', align: 'r' }, { label: 'Cess', align: 'r' }, 'Condition',
        { label: 'Default', align: 'c' }, '']}
        empty="No rates listed yet. Until one is added, the material's own rates are used.">
        {rows.map(r => (
          <tr key={r.id}>
            <td><b>{r.label}</b></td>
            <td className="r mono">{r.sgst_pct}%</td>
            <td className="r mono">{r.cgst_pct}%</td>
            <td className="r mono"><b>{r.igst_pct}%</b></td>
            <td className="r mono">{r.cess_pct ? r.cess_pct + '%' : '—'}</td>
            <td className="fine">{r.condition_note || '—'}</td>
            <td className="c">{r.is_default ? <Tag kind="ok">Default</Tag> : ''}</td>
            <td className="r"><button type="button" className="rm" onClick={async () => {
              try { await api.delHsnRate(r.id); load() } catch (x) { setErr(x.message) }
            }}>×</button></td>
          </tr>))}
      </Table>

      <div className="row" style={{ marginTop: 14 }}>
        <Field label="Rate label" hint="What the person invoicing will see">
          <input value={f.label} placeholder="Concessional 5%"
            onChange={e => set('label', e.target.value)} /></Field>
        <Field label="SGST %"><input className="mono" type="number" step="0.01"
          value={f.sgst_pct} onChange={e => set('sgst_pct', e.target.value)} /></Field>
        <Field label="CGST %"><input className="mono" type="number" step="0.01"
          value={f.cgst_pct} onChange={e => set('cgst_pct', e.target.value)} /></Field>
        <Field label="IGST %"><input className="mono" type="number" step="0.01"
          value={f.igst_pct} onChange={e => set('igst_pct', e.target.value)} /></Field>
        <Field label="Cess %"><input className="mono" type="number" step="0.01"
          value={f.cess_pct} onChange={e => set('cess_pct', e.target.value)} /></Field>
      </div>
      <div style={{ marginTop: 12 }}>
        <Field label="Condition that earns this rate"
          hint="For example: where input tax credit is not taken">
          <input value={f.condition_note}
            onChange={e => set('condition_note', e.target.value)} /></Field>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12,
        cursor: 'pointer' }}>
        <input type="checkbox" checked={f.is_default} style={{ width: 16, height: 16 }}
          onChange={e => set('is_default', e.target.checked)} />
        Offer this one first on the invoice
      </label>
      {mismatch && <Alert kind="warn">SGST {f.sgst_pct}% plus CGST {f.cgst_pct}% is {split}%,
        which does not equal IGST {f.igst_pct}%. The split and the integrated rate have to come
        to the same thing, or the same supply would be taxed differently depending on which
        state the customer sits in.</Alert>}
      <div className="ft">
        <button type="button" className="btn btn-a" onClick={add}
          disabled={mismatch || !f.label.trim()}>Add rate</button>
        {err && <span className="err">{err}</span>}
      </div>
    </Panel>
  )
}
