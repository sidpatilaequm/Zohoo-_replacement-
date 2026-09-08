import { useState } from 'react'
import { Field, Table, Tag } from './ui'

/** PAN, MSME, bank and contact people — identical on both party masters. */
export function PanMsme({ f, set }) {
  return (
    <div className="row" style={{ marginTop: 13 }}>
      <Field label="PAN" hint="Ten characters: five letters, four digits, a letter">
        <input className="mono" maxLength={10} value={f.pan}
          onChange={e => set('pan', e.target.value.toUpperCase())} /></Field>
      <Field label="MSME registered">
        <select value={f.msme_registered ? 'Y' : 'N'}
          onChange={e => set('msme_registered', e.target.value === 'Y')}>
          <option value="N">No</option><option value="Y">Yes</option></select></Field>
      <Field label="Udyam or MSME number"
        hint={f.msme_registered ? 'Required once the flag is set' : 'Not applicable'}>
        <input className="mono" value={f.msme_number} disabled={!f.msme_registered}
          onChange={e => set('msme_number', e.target.value)} /></Field>
    </div>)
}

export function BankBlock({ f, set, banks }) {
  const ifscOk = !f.bank_ifsc || /^[A-Z]{4}0[A-Z0-9]{6}$/.test(f.bank_ifsc)
  return (<>
    <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
      color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>Bank details</h3>
    <div className="row">
      <Field label="Bank name">
        <select value={f.bank_name} onChange={e => set('bank_name', e.target.value)}>
          <option value="">— select —</option>
          {banks.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
        </select></Field>
      <Field label="IFSC code"
        hint={ifscOk ? 'Eleven characters, e.g. SBIN0040807' : 'That is not a valid IFSC'}>
        <input className={'mono' + (ifscOk ? '' : ' err')} maxLength={11} value={f.bank_ifsc}
          onChange={e => set('bank_ifsc', e.target.value.toUpperCase())} /></Field>
      <Field label="Bank account number">
        <input className="mono" value={f.bank_account}
          onChange={e => set('bank_account', e.target.value)} /></Field>
    </div>
  </>)
}

export function Contacts({ contacts, setContacts, designations }) {
  const BLANK = { first_name: '', middle_name: '', last_name: '', designation_id: '',
    phone: '', email: '' }
  const [c, setC] = useState(BLANK)
  const [err, setErr] = useState(null)
  const dName = id => designations.find(d => String(d.id) === String(id))?.name || '—'

  function add() {
    if (!c.first_name.trim()) return setErr('A contact needs at least a first name')
    if (c.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email))
      return setErr('That is not a valid email address')
    setContacts([...contacts, { ...c, designation_id: c.designation_id
      ? Number(c.designation_id) : null, is_primary: contacts.length === 0 }])
    setC(BLANK); setErr(null)
  }
  return (<>
    <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
      color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>Contact people</h3>
    <Table head={['First name', 'Middle name', 'Last name', 'Designation', 'Phone', 'Email',
      { label: 'Primary', align: 'c' }, '']}>
      {contacts.map((x, i) => (
        <tr key={i}>
          <td>{x.first_name}</td><td>{x.middle_name || '—'}</td><td>{x.last_name || '—'}</td>
          <td>{dName(x.designation_id)}</td>
          <td className="mono">{x.phone || '—'}</td>
          <td className="mono fine">{x.email || '—'}</td>
          <td className="c"><input type="radio" checked={!!x.is_primary}
            onChange={() => setContacts(contacts.map((y, j) =>
              ({ ...y, is_primary: i === j })))} /></td>
          <td className="r"><button type="button" className="rm"
            onClick={() => setContacts(contacts.filter((_, j) => j !== i))}>×</button></td>
        </tr>))}
    </Table>
    <div className="row" style={{ marginTop: 10 }}>
      <Field label="First name"><input value={c.first_name}
        onChange={e => setC({ ...c, first_name: e.target.value })} /></Field>
      <Field label="Middle name"><input value={c.middle_name}
        onChange={e => setC({ ...c, middle_name: e.target.value })} /></Field>
      <Field label="Last name"><input value={c.last_name}
        onChange={e => setC({ ...c, last_name: e.target.value })} /></Field>
      <Field label="Designation">
        <select value={c.designation_id}
          onChange={e => setC({ ...c, designation_id: e.target.value })}>
          <option value="">— select —</option>
          {designations.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select></Field>
      <Field label="Phone number"><input className="mono" value={c.phone}
        onChange={e => setC({ ...c, phone: e.target.value })} /></Field>
      <Field label="Email address"><input value={c.email}
        onChange={e => setC({ ...c, email: e.target.value })} /></Field>
    </div>
    <div className="ft" style={{ marginTop: 8 }}>
      <button type="button" className="btn btn-sm" onClick={add}>Add contact</button>
      {err && <span className="err">{err}</span>}
    </div>
  </>)
}

export function ContactCell({ contacts }) {
  if (!contacts?.length) return <span className="fine">—</span>
  return contacts.map(c => (
    <div key={c.id} className="fine">
      <b>{[c.first_name, c.middle_name, c.last_name].filter(Boolean).join(' ')}</b>
      {c.designation ? ` · ${c.designation}` : ''}
      {c.phone ? ` · ${c.phone}` : ''}
      {c.is_primary ? ' · primary' : ''}
    </div>))
}

export function BankCell({ p }) {
  if (!p.bank_name) return <span className="fine">—</span>
  return (<div className="fine">{p.bank_name}
    <div className="mono">{p.bank_ifsc || ''} {p.bank_account || ''}</div></div>)
}

export function MsmeTag({ p }) {
  return p.msme_registered
    ? <Tag kind="ok">{p.msme_number || 'MSME'}</Tag>
    : <Tag>No</Tag>
}
