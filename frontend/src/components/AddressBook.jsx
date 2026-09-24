import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert } from './ui'

const BLANK = {
  label: '', addr_type: 'BOTH', gstin: '', addr: '', city: '',
  state_code: '29', pin: '', contact: '', phone: '', is_default: false,
}

/**
 * Addresses beyond the one on the party record.
 *
 * The GSTIN belongs to the address rather than only to the party, because a
 * customer with premises in two states holds a separate registration for each,
 * and the place of supply follows whichever one is being billed.
 */
export default function AddressBook({ kind, partyId, states }) {
  const { api } = useAuth()
  const [rows, setRows] = useState([])
  const [f, setF] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  async function load() {
    if (!partyId) { setRows([]); return }
    try { setRows(await api.addresses(kind, partyId)) }
    catch (x) { setErr(x.message) }
  }
  useEffect(() => { load() /* eslint-disable-next-line */ }, [kind, partyId])

  if (!partyId) return (
    <Alert kind="warn">Save the record first, then add further addresses to it.</Alert>)

  async function save(e) {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const body = { ...f, gstin: f.gstin.trim() || null, pin: f.pin.trim() || null,
        contact: f.contact.trim() || null, phone: f.phone.trim() || null }
      if (editing) await api.editAddress(editing, body)
      else await api.addAddress(kind, partyId, body)
      setF(BLANK); setEditing(null); load()
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  async function remove(id) {
    try { await api.delAddress(id); load() } catch (x) { setErr(x.message) }
  }

  const stName = c => (states || []).find(s => s.code === c)?.name || c

  return (
    <Panel title={`Additional addresses — ${rows.length}`}>
      <Alert kind="ok">One party can have several addresses. Each carries its own state and
        its own GSTIN, and the invoice picks which one to bill and which to deliver to. The
        place of supply follows the address chosen, and can still be overridden on the
        invoice itself.</Alert>

      <Table head={['Label', { label: 'Use for', align: 'c' }, 'Address', 'State',
        'GSTIN', 'Contact', { label: 'Default', align: 'c' }, '']}
        empty="No further addresses. The one on the record above is used.">
        {rows.map(a => (
          <tr key={a.id}>
            <td><b>{a.label}</b></td>
            <td className="c"><Tag kind={a.addr_type === 'BOTH' ? 'ok' : 'warn'}>
              {a.addr_type === 'BOTH' ? 'Bill and ship'
                : a.addr_type === 'BILLING' ? 'Billing' : 'Shipping'}</Tag></td>
            <td className="fine">{a.addr}, {a.city} {a.pin || ''}</td>
            <td className="mono">{a.state_code} — {stName(a.state_code)}</td>
            <td className="mono">{a.gstin || '—'}</td>
            <td className="fine">{a.contact || '—'}{a.phone ? ` · ${a.phone}` : ''}</td>
            <td className="c">{a.is_default ? <Tag kind="ok">Default</Tag> : ''}</td>
            <td className="r" style={{ whiteSpace: 'nowrap' }}>
              <button type="button" className="btn btn-sm" onClick={() => {
                setEditing(a.id)
                setF({ label: a.label, addr_type: a.addr_type, gstin: a.gstin || '',
                  addr: a.addr, city: a.city, state_code: a.state_code, pin: a.pin || '',
                  contact: a.contact || '', phone: a.phone || '',
                  is_default: a.is_default })
              }}>Edit</button>
              <button type="button" className="rm"
                onClick={() => remove(a.id)}>×</button></td>
          </tr>))}
      </Table>

      <div className="row" style={{ marginTop: 14 }}>
        <Field label="Label" hint="Head office, Plant 2, Chennai branch">
          <input value={f.label} onChange={e => set('label', e.target.value)} /></Field>
        <Field label="Use for">
          <select value={f.addr_type} onChange={e => set('addr_type', e.target.value)}>
            <option value="BOTH">Billing and shipping</option>
            <option value="BILLING">Billing only</option>
            <option value="SHIPPING">Shipping only</option>
          </select></Field>
        <Field label="Address">
          <input value={f.addr} onChange={e => set('addr', e.target.value)} /></Field>
        <Field label="City">
          <input value={f.city} onChange={e => set('city', e.target.value)} /></Field>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <Field label="State" hint="Decides the place of supply when this address is billed">
          <select value={f.state_code} onChange={e => set('state_code', e.target.value)}>
            {(states || []).map(s => (
              <option key={s.code} value={s.code}>{s.code} — {s.name}</option>))}
          </select></Field>
        <Field label="GSTIN at this address"
          hint="Must begin with the state code above">
          <input className="mono" maxLength={15} value={f.gstin}
            onChange={e => set('gstin', e.target.value.toUpperCase())} /></Field>
        <Field label="PIN">
          <input className="mono" maxLength={6} value={f.pin}
            onChange={e => set('pin', e.target.value)} /></Field>
        <Field label="Contact person">
          <input value={f.contact} onChange={e => set('contact', e.target.value)} /></Field>
        <Field label="Phone">
          <input className="mono" value={f.phone}
            onChange={e => set('phone', e.target.value)} /></Field>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12,
        cursor: 'pointer' }}>
        <input type="checkbox" checked={f.is_default} style={{ width: 16, height: 16 }}
          onChange={e => set('is_default', e.target.checked)} />
        Use this address by default on new documents
      </label>
      <div className="ft">
        <button type="button" className="btn btn-a" onClick={save}
          disabled={busy || !f.label.trim() || !f.addr.trim() || !f.city.trim()}>
          {editing ? 'Save changes' : 'Add address'}</button>
        {editing && <button type="button" className="btn"
          onClick={() => { setF(BLANK); setEditing(null) }}>Cancel</button>}
        {err && <span className="err">{err}</span>}
      </div>
    </Panel>
  )
}
