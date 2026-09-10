import { useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { PanMsme, BankBlock, Contacts, ContactCell, BankCell, MsmeTag } from '../components/PartyExtras'

const BLANK = { code: '', name: '', party_type: 'B2B', bill_addr: '', bill_city: '',
  bill_state: '29', bill_pin: '', ship_same: true, ship_addr: '', ship_city: '',
  ship_state: '29', ship_pin: '', email: '',
  pan: '', msme_registered: false, msme_number: '',
  bank_name: '', bank_ifsc: '', bank_account: '' }

export default function Customers() {
  const { api } = useAuth()
  const list = useLoad(() => api.customers())
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
      try { await api.customerLogo(id, r.result); list.reload(); showFlash('Logo saved — it prints on every document for this customer.') }
      catch (x) { showFlash(x.message, 'bad') }
    }
    r.readAsDataURL(file)
  }   // id of the customer being edited
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  function edit(c) {
    setEditing(c.id)
    setF({ ...BLANK, ...Object.fromEntries(Object.keys(BLANK).map(k => [k, c[k] ?? BLANK[k]])) })
    setRegs(c.gstins.map(r => ({ gstin: r.gstin, label: r.label || '', is_default: r.is_default })))
    setContacts(c.contacts.map(x => ({ first_name: x.first_name, middle_name: x.middle_name || '', last_name: x.last_name || '',
      designation_id: x.designation_id || '', phone: x.phone || '', email: x.email || '', is_primary: x.is_primary })))
    setErr(null); window.scrollTo({ top: 0 })
  }
  function cancelEdit() { setEditing(null); setF(BLANK); setRegs([]); setContacts([]); setErr(null) }

  function addReg() {
    const v = g.gstin.trim().toUpperCase()
    if (v.length !== 15) return setErr('A GSTIN is exactly 15 characters')
    if (!/^\d{2}/.test(v)) return setErr('A GSTIN begins with a two-digit state code')
    if (regs.some(r => r.gstin === v)) return setErr('That GSTIN is already on this customer')
    setRegs([...regs, { gstin: v, label: g.label, is_default: !regs.length }])
    setG({ gstin: '', label: '' }); setErr(null)
  }
  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const body = { ...f, code: f.code || null, gstins: regs, contacts }
      if (editing) await api.editCustomer(editing, body); else await api.addCustomer(body)
      setEditing(null); setF(BLANK); setRegs([]); setContacts([]); list.reload()
      showFlash(editing ? 'Customer updated.' : 'Customer saved.')
    } catch (x) { setErr(x.message) }
  }
  async function remove(id) {
    try { await api.delCustomer(id); list.reload() }
    catch (x) { showFlash(x.message, 'bad') }
  }

  if (list.loading || states.loading || banks.loading || desigs.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>
  const stateName = c => states.data?.find(s => s.code === c)?.name || c

  return (<>
    {flash}
    <Panel title={editing ? `Edit customer ${f.code}` : 'Add customer'}
      right={editing && <button type="button" className="btn btn-sm" onClick={cancelEdit}>Cancel edit</button>}>
      <form onSubmit={save}>
        <div className="row">
          <Field label="Customer code" hint="Left blank, one is allocated">
            <input className="mono" value={f.code} onChange={e => set('code', e.target.value)} /></Field>
          <Field label="Customer name">
            <input value={f.name} onChange={e => set('name', e.target.value)} required /></Field>
          <Field label="Customer type"
            hint={f.party_type === 'B2C' ? 'Reported in GSTR-1 under b2cs' : 'GSTIN required'}>
            <select value={f.party_type} onChange={e => {
              set('party_type', e.target.value); if (e.target.value === 'B2C') setRegs([]) }}>
              <option value="B2B">B2B — registered</option>
              <option value="B2C">B2C — unregistered</option></select></Field>
          <Field label="Email" hint="Used when sending the invoice">
            <input value={f.email} onChange={e => set('email', e.target.value)} /></Field>
        </div>

        <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
          color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>Billing address</h3>
        <div className="row">
          <Field label="Address"><input value={f.bill_addr}
            onChange={e => set('bill_addr', e.target.value)} required /></Field>
          <Field label="City"><input value={f.bill_city}
            onChange={e => set('bill_city', e.target.value)} required /></Field>
          <Field label="State"><select value={f.bill_state}
            onChange={e => set('bill_state', e.target.value)}>
            {states.data.map(s => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
          </select></Field>
          <Field label="PIN"><input className="mono" maxLength={6} value={f.bill_pin}
            onChange={e => set('bill_pin', e.target.value)} /></Field>
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 9, margin: '16px 0 8px',
          cursor: 'pointer' }}>
          <input type="checkbox" checked={f.ship_same} style={{ width: 16, height: 16 }}
            onChange={e => set('ship_same', e.target.checked)} />
          Delivery address is the same as the billing address
        </label>
        {!f.ship_same && (
          <div className="row">
            <Field label="Delivery address"><input value={f.ship_addr}
              onChange={e => set('ship_addr', e.target.value)} /></Field>
            <Field label="City"><input value={f.ship_city}
              onChange={e => set('ship_city', e.target.value)} /></Field>
            <Field label="State"><select value={f.ship_state}
              onChange={e => set('ship_state', e.target.value)}>
              {states.data.map(s => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
            </select></Field>
            <Field label="PIN"><input className="mono" maxLength={6} value={f.ship_pin}
              onChange={e => set('ship_pin', e.target.value)} /></Field>
          </div>)}

        {f.party_type === 'B2B' ? (<>
          <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
            color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>GST registrations</h3>
          <p className="fine" style={{ margin: '0 0 9px' }}>
            A GSTIN belongs to one state. Add one row per registration; the invoice screen
            lets you pick which one to bill under.</p>
          <Table head={['GSTIN', 'State', 'Label', { label: 'Default', align: 'c' }, '']}>
            {regs.map((r, i) => (
              <tr key={r.gstin}>
                <td className="mono">{r.gstin}</td>
                <td>{stateName(r.gstin.slice(0, 2))}</td>
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
            <input placeholder="label, e.g. Head office"
              style={{ padding: '8px 11px', border: '1px solid var(--line2)', borderRadius: 7, width: 190 }}
              value={g.label} onChange={e => setG({ ...g, label: e.target.value })} />
            <button type="button" className="btn btn-sm" onClick={addReg}>Add registration</button>
          </div>
        </>) : (
          <Alert kind="warn"><b>B2C customer.</b> No GSTIN is held or required. These supplies
            are reported under b2cs, or b2cl where an inter-state invoice exceeds ₹2,50,000.</Alert>)}

        <PanMsme f={f} set={set} />
        <BankBlock f={f} set={set} banks={banks.data} />
        <Contacts contacts={contacts} setContacts={setContacts} designations={desigs.data} />
        <div className="ft"><button className="btn btn-a">{editing ? 'Update customer' : 'Save customer'}</button>
          {err && <span className="err">{err}</span>}</div>
      </form>
    </Panel>

    <Panel title={`Customers — ${list.data.length}`} bodyless>
      <Table head={['Code', 'Name', { label: 'Type', align: 'c' }, 'Registrations', 'PAN',
        { label: 'MSME', align: 'c' }, 'Bank', 'Contact', 'Billing', '']}
        empty="No customers yet.">
        {list.data.map(c => (
          <tr key={c.id}>
            <td className="mono">{c.code}</td>
            <td style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {c.logo ? <img src={c.logo} alt="" style={{ height: 26, maxWidth: 60, objectFit: 'contain', border: '1px solid var(--line)', borderRadius: 4 }} />
                : <span className="fine" style={{ fontSize: 11 }}>no logo</span>}
              <div><b>{c.name}</b>{c.email && <div className="fine">{c.email}</div>}</div></td>
            <td className="c">{c.party_type === 'B2C'
              ? <Tag kind="warn">B2C</Tag> : <Tag kind="ok">B2B</Tag>}</td>
            <td>{c.gstins.length
              ? c.gstins.map(r => <div key={r.id} className="mono" style={{ fontSize: 11.5 }}>
                  {r.gstin} <span className="fine">{stateName(r.state_code)}
                  {r.is_default ? ' · default' : ''}</span></div>)
              : <Tag>Unregistered</Tag>}</td>
            <td className="mono fine">{c.pan || '—'}</td>
            <td className="c"><MsmeTag p={c} /></td>
            <td><BankCell p={c} /></td>
            <td><ContactCell contacts={c.contacts} /></td>
            <td className="fine">{c.bill_addr}, {c.bill_city} {c.bill_pin}
              {!c.ship_same && <div>ships to {c.ship_city}</div>}</td>
            <td className="r" style={{ whiteSpace: 'nowrap' }}>
              <button className="btn btn-sm" onClick={() => edit(c)}>Edit</button>
              <button className="btn btn-sm" style={{ marginLeft: 4 }} title="Upload this customer's logo; it prints on their documents"
                onClick={() => { logoRef.current.dataset.id = c.id; logoRef.current.click() }}>{c.logo ? 'Change logo' : 'Logo'}</button>
              {c.logo && <button className="btn btn-sm" style={{ marginLeft: 4 }} onClick={async () => {
                try { await api.customerLogo(c.id, null); list.reload() } catch (x) { showFlash(x.message, 'bad') } }}>Remove logo</button>}
              <button className="rm" style={{ marginLeft: 4 }} onClick={() => remove(c.id)}>×</button></td>
          </tr>))}
      </Table>
    </Panel>
    <input type="file" ref={logoRef} accept="image/*" style={{ display: 'none' }} onChange={pickLogo} />
  </>)
}
