import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'

const BLANK = { emp_code: '', first_name: '', last_name: '', email: '', active: true }

export default function Employees() {
  const { api } = useAuth()
  const list = useLoad(() => api.employees())
  const [f, setF] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState(null)
  const [q, setQ] = useState('')
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      if (editing) await api.editEmployee(editing, f); else await api.addEmployee(f)
      showFlash(editing ? 'Employee updated.' : 'Employee added.')
      setF(BLANK); setEditing(null); list.reload()
    } catch (x) { setErr(x.message) }
  }

  function edit(e) {
    setEditing(e.id); setErr(null)
    setF({ emp_code: e.emp_code, first_name: e.first_name, last_name: e.last_name,
      email: e.email, active: e.active })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function remove(e) {
    if (!window.confirm(`Delete ${e.name} (${e.emp_code})?`)) return
    try { await api.delEmployee(e.id); list.reload(); showFlash('Employee deleted.') }
    catch (x) { showFlash(x.message, 'bad') }
  }

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  const needle = q.trim().toLowerCase()
  const rows = (list.data || []).filter(e => !needle ||
    [e.emp_code, e.name, e.email].some(v => v.toLowerCase().includes(needle)))

  return (<>
    {flash}
    <Alert kind="ok"><b>People the company pays.</b> Add each employee once. On the Bank
      Statements screen, a salary payment or a reimbursed expense can then be attached to the
      employee it went to, and the month's totals appear in the expense ledger.</Alert>

    <form onSubmit={save}>
      <Panel title={editing ? 'Edit employee' : 'Add an employee'}>
        <div className="row">
          <Field label="Employee ID" hint="Your own reference, e.g. E001">
            <input className="mono" maxLength={20} value={f.emp_code} required
              onChange={e => set('emp_code', e.target.value)} /></Field>
          <Field label="First name"><input maxLength={60} value={f.first_name} required
            onChange={e => set('first_name', e.target.value)} /></Field>
          <Field label="Last name"><input maxLength={60} value={f.last_name} required
            onChange={e => set('last_name', e.target.value)} /></Field>
          <Field label="Email"><input type="email" maxLength={160} value={f.email} required
            onChange={e => set('email', e.target.value)} /></Field>
        </div>
        <div className="ft">
          <button className="btn btn-a">{editing ? 'Save changes' : 'Add employee'}</button>
          {editing && <>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12.5 }}>
              <input type="checkbox" checked={f.active}
                onChange={e => set('active', e.target.checked)} />
              Active — can be picked on bank transactions</label>
            <button type="button" className="btn"
              onClick={() => { setF(BLANK); setEditing(null); setErr(null) }}>Cancel</button></>}
          {err && <span className="err">{err}</span>}
        </div>
      </Panel>
    </form>

    <Panel title="Employees" right={
      <input placeholder="Search ID, name or email" value={q} onChange={e => setQ(e.target.value)}
        style={{ padding: '6px 10px', border: '1px solid var(--line2)', borderRadius: 7, width: 220 }} />}>
      <Table head={['Employee ID', 'First name', 'Last name', 'Email', 'Status',
        { label: 'Bank entries', align: 'r' }, '']}
        empty={needle ? 'No employee matches that search.' : 'No employees yet. Add the first one above.'}>
        {rows.map(e => <tr key={e.id}>
          <td className="mono">{e.emp_code}</td><td>{e.first_name}</td><td>{e.last_name}</td>
          <td>{e.email}</td>
          <td>{e.active ? <Tag kind="ok">active</Tag> : <Tag kind="no">inactive</Tag>}</td>
          <td className="r">{e.links || '—'}</td>
          <td className="r" style={{ whiteSpace: 'nowrap' }}>
            <button type="button" className="btn btn-sm" onClick={() => edit(e)}>Edit</button>
            <button type="button" className="btn btn-sm" style={{ marginLeft: 5 }}
              disabled={e.links > 0} onClick={() => remove(e)}
              title={e.links > 0 ? 'Has bank entries — mark inactive instead' : 'Delete'}>Delete</button>
          </td></tr>)}
      </Table>
    </Panel>
  </>)
}
