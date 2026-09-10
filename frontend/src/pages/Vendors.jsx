import { useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { PanMsme, BankBlock, Contacts, ContactCell, BankCell, MsmeTag } from '../components/PartyExtras'

const BLANK = { code: '', name: '', party_type: 'B2B', addr: '', city: '',
  state_code: '29', pin: '', email: '',
  pan: '', msme_registered: false, msme_number: '',
  bank_name: '', bank_ifsc: '', bank_account: '' }

export default function Vendors() {
  const { api } = useAuth()
  const list = useLoad(() => api.vendors())
  const states = useLoad(() => api.states())
  const banks = useLoad(() => api.banks())
  const desigs = useLoad(() => api.designations())
  const [contacts, setContacts] = useState([])
  const [f, setF] = useState(BLANK)
  const [regs, setRegs] = useState([])
  const [g, setG] = useState({ gstin: '', label: '' })
  const [err, setErr] = useState(null)
  const [editing, setEditing] = useState(null)
  const logoRef = useRef(null)
  function pickLogo(e) {
    const file = e.target.files?.[0], id = Number(e.target.dataset.id); e.target.value = ''
    if (!file || !id) return
    if (file.size > 500 * 1024) return showFlash('That file is over 500 KB.', 'bad')
    const r = new FileReader()
    r.onload = async () => {
      try { await api.vendorLogo(id, r.result); list.reload(); showFlash('Logo saved — it prints on every document for this vendor.') }
      catch (x) { showFlash(x.message, 'bad') }
    }
    r.readAsDataURL(file)
  }
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  function edit(v) {
    setEditing(v.id)
    setF({ ...BLANK, ...Object.fromEntries(Object.keys(BLANK).map(k => [k, v[k] ?? BLANK[k]])), tds_section: v.tds_section || '', tds_rate: v.tds_rate ?? 0 })
    setRegs(v.gstins.map(r => ({ gstin: r.gstin, label: r.label || '', is_default: r.is_default })))
    setContacts(v.contacts.map(x => ({ first_name: x.first_name, middle_name: x.middle_name || '', last_name: x.last_name || '',
      designation_id: x.designation_id || '', phone: x.phone || '', email: x.email || '', is_primary: x.is_primary })))
    setErr(null); window.scrollTo({ top: 0 })
  }
  function cancelEdit() { setEditing(null); setF(BLANK); setRegs([]); setContacts([]); setErr(null) }

  function addReg() {
    const v = g.gstin.trim().toUpperCase()
    if (v.length !== 15) return setErr('A GSTIN is exactly 15 characters')
    if (regs.some(r => r.gstin === v)) return setErr('That GSTIN is already on this vendor')
    setRegs([...regs, { gstin: v, label: g.label, is_default: !regs.length }])
    setG({ gstin: '', label: '' }); setErr(null)
  }
  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const body = { ...f, code: f.code || null, gstins: regs, contacts }
      if (editing) await api.editVendor(editing, body); else await api.addVendor(body)
      setEditing(null); setF(BLANK); setRegs([]); setContacts([]); list.reload()
      showFlash(editing ? 'Vendor updated.' : 'Vendor saved.')
    } catch (x) { setErr(x.message) }
  }
  if (list.loading || states.loading || banks.loading || desigs.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>
  const stateName = c => states.data?.find(s => s.code === c)?.name || c

  return (<>
    {flash}
    <Panel title={editing ? `Edit vendor ${f.code}` : 'Add vendor'}
      right={editing && <button type="button" className="btn btn-sm" onClick={cancelEdit}>Cancel edit</button>}>
      <form onSubmit={save}>
        <div className="row">
          <Field label="Vendor code"><input className="mono" value={f.code}
            onChange={e => set('code', e.target.value)} /></Field>
          <Field label="Vendor name"><input value={f.name}
            onChange={e => set('name', e.target.value)} required /></Field>
          <Field label="Vendor type"
            hint={f.party_type === 'B2C' ? 'No GST charged, no input credit' : 'Input credit available'}>
            <select value={f.party_type} onChange={e => {
              set('party_type', e.target.value); if (e.target.value === 'B2C') setRegs([]) }}>
              <option value="B2B">Registered</option>
              <option value="B2C">Unregistered</option></select></Field>
          <Field label="Email"><input value={f.email}
            onChange={e => set('email', e.target.value)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="Address"><input value={f.addr}
            onChange={e => set('addr', e.target.value)} required /></Field>
          <Field label="City"><input value={f.city}
            onChange={e => set('city', e.target.value)} required /></Field>
          <Field label="State"><select value={f.state_code}
            onChange={e => set('state_code', e.target.value)}>
            {states.data.map(s => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
          </select></Field>
          <Field label="PIN"><input className="mono" maxLength={6} value={f.pin}
            onChange={e => set('pin', e.target.value)} /></Field>
        </div>
        {f.party_type === 'B2B' ? (<>
          <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
            color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>GST registrations</h3>
          <Table head={['GSTIN', 'State', 'Label', { label: 'Default', align: 'c' }, '']}>
            {regs.map((r, i) => (
              <tr key={r.gstin}>
                <td className="mono">{r.gstin}</td><td>{stateName(r.gstin.slice(0, 2))}</td>
                <td>{r.label || '—'}</td>
                <td className="c"><input type="radio" checked={r.is_default}
                  onChange={() => setRegs(regs.map((x, j) => ({ ...x, is_default: i === j })))} /></td>
                <td className="r"><button type="button" className="rm"
                  onClick={() => setRegs(regs.filter((_, j) => j !== i))}>×</button></td>
              </tr>))}
          </Table>
          <div className="ft">
            <input className="mono" placeholder="15-character GSTIN" maxLength={15}
              style={{ padding: '8px 11px', border: '1px solid var(--line2)', borderRadius: 7, width: 190 }}
              value={g.gstin} onChange={e => setG({ ...g, gstin: e.target.value.toUpperCase() })} />
            <input placeholder="label"
              style={{ padding: '8px 11px', border: '1px solid var(--line2)', borderRadius: 7, width: 190 }}
              value={g.label} onChange={e => setG({ ...g, label: e.target.value })} />
            <button type="button" className="btn btn-sm" onClick={addReg}>Add registration</button>
          </div>
        </>) : (
          <Alert kind="warn"><b>Unregistered vendor.</b> No GST is charged, so there is no input
            tax credit. Reverse charge may apply on notified supplies — check before claiming.</Alert>)}
        <PanMsme f={f} set={set} />
        <BankBlock f={f} set={set} banks={banks.data} />
        <Contacts contacts={contacts} setContacts={setContacts} designations={desigs.data} />
        <div className="ft"><button className="btn btn-a">{editing ? 'Update vendor' : 'Save vendor'}</button>
          {err && <span className="err">{err}</span>}</div>
      </form>
    </Panel>

    <Panel title={`Vendors — ${list.data.length}`} bodyless>
      <Table head={['Code', 'Name', { label: 'Type', align: 'c' }, 'Registrations', 'PAN',
        { label: 'MSME', align: 'c' }, 'Bank', 'Contact', 'Address', '']}
        empty="No vendors yet.">
        {list.data.map(v => (
          <tr key={v.id}>
            <td className="mono">{v.code}</td>
            <td style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {v.logo ? <img src={v.logo} alt="" style={{ height: 26, maxWidth: 60, objectFit: 'contain', border: '1px solid var(--line)', borderRadius: 4 }} />
                : <span className="fine" style={{ fontSize: 11 }}>no logo</span>}
              <div><b>{v.name}</b>{v.email && <div className="fine">{v.email}</div>}</div></td>
            <td className="c">{v.party_type === 'B2C'
              ? <Tag kind="warn">Unregistered</Tag> : <Tag kind="ok">Registered</Tag>}</td>
            <td>{v.gstins.length
              ? v.gstins.map(r => <div key={r.id} className="mono" style={{ fontSize: 11.5 }}>
                  {r.gstin} <span className="fine">{stateName(r.state_code)}</span></div>)
              : <Tag>None</Tag>}</td>
            <td className="mono fine">{v.pan || '—'}</td>
            <td className="c"><MsmeTag p={v} /></td>
            <td><BankCell p={v} /></td>
            <td><ContactCell contacts={v.contacts} /></td>
            <td className="fine">{v.addr}, {v.city} {v.pin}</td>
            <td className="r" style={{ whiteSpace: 'nowrap' }}>
              <button className="btn btn-sm" onClick={() => edit(v)}>Edit</button>
              <button className="btn btn-sm" style={{ marginLeft: 4 }} title="Upload this vendor's logo; it prints on their documents"
                onClick={() => { logoRef.current.dataset.id = v.id; logoRef.current.click() }}>{v.logo ? 'Change logo' : 'Logo'}</button>
              {v.logo && <button className="btn btn-sm" style={{ marginLeft: 4 }} onClick={async () => {
                try { await api.vendorLogo(v.id, null); list.reload() } catch (x) { showFlash(x.message, 'bad') } }}>Remove logo</button>}
              <button className="rm" style={{ marginLeft: 4 }} onClick={async () => {
              try { await api.delVendor(v.id); list.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>×</button></td>
          </tr>))}
      </Table>
    </Panel>
    <input type="file" ref={logoRef} accept="image/*" style={{ display: 'none' }} onChange={pickLogo} />
  </>)
}
