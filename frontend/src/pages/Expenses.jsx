import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'

const BLANK = { exp_code: '', name: '', active: true }

export default function Expenses() {
  const { api } = useAuth()
  const list = useLoad(() => api.expenseHeads())
  const [f, setF] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      if (editing) await api.editExpenseHead(editing, f); else await api.addExpenseHead(f)
      showFlash(editing ? 'Expense head updated.' : 'Expense head added.')
      setF(BLANK); setEditing(null); list.reload()
    } catch (x) { setErr(x.message) }
  }

  async function standard() {
    try {
      const r = await api.addStandardHeads()
      showFlash(r.added ? `${r.added} standard expense head(s) added.` : 'The standard heads are already here.')
      list.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }

  async function remove(h) {
    if (!window.confirm(`Delete ${h.exp_code} ${h.name}?`)) return
    try { await api.delExpenseHead(h.id); list.reload(); showFlash('Expense head deleted.') }
    catch (x) { showFlash(x.message, 'bad') }
  }

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>
  const rows = list.data || []

  return (<>
    {flash}
    <Alert kind="ok"><b>The heads expenses are booked to.</b> An employee expense paid from the
      bank is attached to the employee and to one of these heads. The active heads are also the
      categories offered for company spends on director cards.</Alert>

    <form onSubmit={save}>
      <Panel title={editing ? 'Edit expense head' : 'Add an expense head'}
        right={!editing && <button type="button" className="btn btn-sm" onClick={standard}>
          Add the standard heads</button>}>
        <div className="row">
          <Field label="Expense ID" hint="e.g. EXP001">
            <input className="mono" maxLength={20} value={f.exp_code} required
              onChange={e => set('exp_code', e.target.value)} /></Field>
          <Field label="Expense name" hint="e.g. Travel, Staff welfare">
            <input maxLength={80} value={f.name} required
              onChange={e => set('name', e.target.value)} /></Field>
          <Field label=" "><button className="btn btn-a">
            {editing ? 'Save changes' : 'Add expense head'}</button></Field>
        </div>
        {(editing || err) && <div className="ft">
          {editing && <>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12.5 }}>
              <input type="checkbox" checked={f.active}
                onChange={e => set('active', e.target.checked)} />
              Active — offered when allocating expenses</label>
            <button type="button" className="btn"
              onClick={() => { setF(BLANK); setEditing(null); setErr(null) }}>Cancel</button></>}
          {err && <span className="err">{err}</span>}
        </div>}
      </Panel>
    </form>

    <Panel title="Expense heads">
      <Table head={['Expense ID', 'Expense name', 'Status', { label: 'Employee entries', align: 'r' },
        { label: 'Card entries', align: 'r' }, '']}
        empty="No expense heads yet. Add one above, or add the standard heads.">
        {rows.map(h => {
          const used = h.employee_entries + h.card_entries
          return <tr key={h.id}>
            <td className="mono">{h.exp_code}</td><td>{h.name}</td>
            <td>{h.active ? <Tag kind="ok">active</Tag> : <Tag kind="no">inactive</Tag>}</td>
            <td className="r">{h.employee_entries || '—'}</td>
            <td className="r">{h.card_entries || '—'}</td>
            <td className="r" style={{ whiteSpace: 'nowrap' }}>
              <button type="button" className="btn btn-sm" onClick={() => {
                setEditing(h.id); setErr(null)
                setF({ exp_code: h.exp_code, name: h.name, active: h.active })
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}>Edit</button>
              <button type="button" className="btn btn-sm" style={{ marginLeft: 5 }}
                disabled={used > 0} onClick={() => remove(h)}
                title={used ? 'In use — mark inactive instead' : 'Delete'}>Delete</button>
            </td></tr>})}
      </Table>
    </Panel>
  </>)
}
