import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { PERM_LABEL, ALL_PERMS } from '../lib/menu'

export default function Users() {
  const { api, me } = useAuth()
  const users = useLoad(() => api.users())
  const groups = useLoad(() => api.groups())
  const [u, setU] = useState({ name: '', email: '', password: '', group_id: '' })
  const [g, setG] = useState({ name: '', perms: new Set() })
  const [gEdit, setGEdit] = useState(null)
  const [uErr, setUErr] = useState(null)
  const [gErr, setGErr] = useState(null)
  const [flash, showFlash] = useFlash()

  if (users.loading || groups.loading) return <Loading />
  if (users.error) return <ErrorBox>{users.error}</ErrorBox>

  const pending = users.data.filter(x => x.pending)
  const members = users.data.filter(x => !x.pending)

  async function addUser(e) {
    e.preventDefault(); setUErr(null)
    try {
      await api.addUser({ ...u, group_id: Number(u.group_id) })
      setU({ name: '', email: '', password: '', group_id: '' })
      users.reload(); showFlash('User added.')
    } catch (x) { setUErr(x.message) }
  }
  async function saveGroup(e) {
    e.preventDefault(); setGErr(null)
    try {
      const body = { name: g.name, perms: [...g.perms] }
      if (gEdit) await api.editGroup(gEdit, body)
      else await api.addGroup(body)
      setG({ name: '', perms: new Set() }); setGEdit(null)
      groups.reload(); users.reload(); showFlash('Group saved.')
    } catch (x) { setGErr(x.message) }
  }
  async function setRole(uid, gid) {
    try { await api.setRole(uid, gid ? Number(gid) : null); users.reload() }
    catch (x) { showFlash(x.message, 'bad') }
  }

  return (<>
    {flash}
    {pending.length > 0 && (
      <Alert kind="warn">
        <b>{pending.length} account{pending.length === 1 ? '' : 's'} waiting for approval.</b>
        {pending.map(p => (
          <div key={p.id} style={{ marginTop: 7, display: 'flex', gap: 8,
            alignItems: 'center', flexWrap: 'wrap' }}>
            <span>{p.name} &lt;{p.email}&gt; asked to join</span>
            <select id={`pg-${p.id}`} defaultValue=""
              style={{ padding: '4px 8px', border: '1px solid var(--line2)', borderRadius: 6 }}>
              <option value="">choose a group</option>
              {groups.data.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
            <button className="btn btn-sm btn-a" onClick={() => {
              const v = document.getElementById(`pg-${p.id}`).value
              if (!v) return showFlash('Choose a group first.', 'bad')
              setRole(p.id, v)
            }}>Approve</button>
            <button className="btn btn-sm" onClick={async () => {
              try { await api.rejectPending(p.id); users.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>Reject</button>
          </div>))}
      </Alert>)}

    <Alert kind="ok"><b>Access is enforced by the API, not by this page.</b> Hiding a menu is a
      convenience; the server checks the group on every request, so a hidden screen cannot be
      reached by editing the browser.</Alert>

    <div className="grid2">
      <form onSubmit={addUser}>
        <Panel title="Add a user to this organisation">
          <div className="row c2">
            <Field label="Full name"><input value={u.name}
              onChange={e => setU({ ...u, name: e.target.value })} required /></Field>
            <Field label="Email"><input value={u.email}
              onChange={e => setU({ ...u, email: e.target.value })} required /></Field>
          </div>
          <div className="row c2" style={{ marginTop: 12 }}>
            <Field label="Password" hint="At least 8 characters">
              <input type="password" value={u.password}
                onChange={e => setU({ ...u, password: e.target.value })} required /></Field>
            <Field label="Group"><select value={u.group_id} required
              onChange={e => setU({ ...u, group_id: e.target.value })}>
              <option value="">— choose —</option>
              {groups.data.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select></Field>
          </div>
          <div className="ft"><button className="btn btn-a">Add user</button>
            {uErr && <span className="err">{uErr}</span>}</div>
          <p className="fine" style={{ marginTop: 8 }}>If that email already has an account
            elsewhere, they are added to this organisation with the group you choose.</p>
        </Panel>
      </form>

      <form onSubmit={saveGroup}>
        <Panel title={gEdit ? 'Edit group' : 'Add group'}>
          <Field label="Group name"><input value={g.name}
            onChange={e => setG({ ...g, name: e.target.value })} required /></Field>
          <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
            color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>Menu access</h3>
          <div className="perm">
            {ALL_PERMS.map(p => (
              <label key={p}>
                <input type="checkbox" checked={g.perms.has(p)} onChange={e => {
                  const n = new Set(g.perms)
                  e.target.checked ? n.add(p) : n.delete(p)
                  setG({ ...g, perms: n })
                }} /> {PERM_LABEL[p]}</label>))}
          </div>
          <div className="ft"><button className="btn btn-a">Save group</button>
            {gEdit && <button type="button" className="btn" onClick={() => {
              setG({ name: '', perms: new Set() }); setGEdit(null) }}>Cancel</button>}
            {gErr && <span className="err">{gErr}</span>}</div>
        </Panel>
      </form>
    </div>

    <Panel title={`Members — ${members.length}`} bodyless>
      <Table head={['Name', 'Email', 'Group', { label: 'Menus', align: 'c' }, '']}
        empty="No members yet.">
        {members.map(m => (
          <tr key={m.id}>
            <td><b>{m.name}</b>{m.id === me?.user?.id && <Tag kind="ok"> you</Tag>}</td>
            <td className="mono fine">{m.email}</td>
            <td><select value={m.group_id || ''} onChange={e => setRole(m.id, e.target.value)}
              style={{ padding: '5px 9px', border: '1px solid var(--line2)', borderRadius: 6 }}>
              {groups.data.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select></td>
            <td className="c mono">{m.perms.length}</td>
            <td className="r">{m.id !== me?.user?.id &&
              <button className="rm" onClick={() => setRole(m.id, null)}>×</button>}</td>
          </tr>))}
      </Table>
    </Panel>

    <Panel title={`Groups — ${groups.data.length}`} bodyless>
      <Table head={['Group', { label: 'Menus', align: 'c' }, 'Access',
        { label: 'In use', align: 'c' }, '']}>
        {groups.data.map(x => (
          <tr key={x.id}>
            <td><b>{x.name}</b></td>
            <td className="c mono">{x.perms.length}</td>
            <td className="fine">{x.perms.map(p => PERM_LABEL[p]).filter(Boolean).join(', ')}</td>
            <td className="c">{x.users
              ? <Tag kind="ok">{x.users} user{x.users === 1 ? '' : 's'}</Tag>
              : <Tag>unused</Tag>}</td>
            <td className="r">
              <button className="btn btn-sm" onClick={() => {
                setGEdit(x.id); setG({ name: x.name, perms: new Set(x.perms) })
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}>Edit</button>
              {!x.users && <button className="rm" onClick={async () => {
                try { await api.delGroup(x.id); groups.reload() }
                catch (e) { showFlash(e.message, 'bad') } }}>×</button>}
            </td>
          </tr>))}
      </Table>
    </Panel>
  </>)
}
