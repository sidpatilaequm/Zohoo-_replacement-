import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'

const TYPES = [
  ['LIST',  'Dropdown — one value from a list'],
  ['MULTI', 'Multiple choice — any number from a list'],
  ['TEXT',  'Text'], ['NUM', 'Numeric'], ['DATE', 'Date'],
]
const TYPE_LABEL = Object.fromEntries(TYPES.map(([k, v]) => [k, v.split(' —')[0]]))

export default function Attributes() {
  const { api } = useAuth()
  const list = useLoad(() => api.attributes())
  const [f, setF] = useState({ code: '', name: '', attr_type: 'LIST' })
  const [values, setValues] = useState([])
  const [nv, setNv] = useState('')
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const listy = ['LIST', 'MULTI'].includes(f.attr_type)

  function reset() {
    setF({ code: '', name: '', attr_type: 'LIST' }); setValues([])
    setNv(''); setEditing(null); setErr(null)
  }
  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const body = { ...f, values: listy ? values : [] }
      if (editing) await api.editAttribute(editing, body)
      else await api.addAttribute(body)
      reset(); list.reload(); showFlash('Attribute saved.')
    } catch (x) { setErr(x.message) }
  }
  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <Alert kind="ok"><b>Attribute definitions are shared across every organisation.</b> A material
      master has the same shape everywhere; only the values differ per material. Editing a
      definition here changes it for all company sets.</Alert>

    <form onSubmit={save}>
      <Panel title={editing ? 'Edit attribute' : 'Add attribute'}>
        <div className="row">
          <Field label="Attribute code">
            <input className="mono" value={f.code} required
              onChange={e => setF({ ...f, code: e.target.value.toUpperCase() })} /></Field>
          <Field label="Attribute name">
            <input value={f.name} required
              onChange={e => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Type">
            <select value={f.attr_type}
              onChange={e => setF({ ...f, attr_type: e.target.value })}>
              {TYPES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></Field>
        </div>
        {listy && (<>
          <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
            color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>Permitted values</h3>
          <div style={{ marginBottom: 9 }}>
            {values.length ? values.map((v, i) => (
              <span key={v} className="tag ok" style={{ margin: '0 6px 6px 0', display: 'inline-flex' }}>
                {v}<button type="button" className="rm" style={{ padding: '0 3px' }}
                  onClick={() => setValues(values.filter((_, j) => j !== i))}>×</button></span>))
              : <span className="fine">No values yet. A dropdown needs at least one.</span>}
          </div>
          <div className="ft" style={{ marginTop: 0 }}>
            <input value={nv} placeholder="add a value"
              style={{ padding: '8px 11px', border: '1px solid var(--line2)',
                borderRadius: 7, width: 240 }}
              onChange={e => setNv(e.target.value)} />
            <button type="button" className="btn btn-sm" onClick={() => {
              const v = nv.trim()
              if (!v) return setErr('Type a value first')
              if (values.includes(v)) return setErr('That value is already listed')
              setValues([...values, v]); setNv(''); setErr(null)
            }}>Add value</button>
          </div>
        </>)}
        <div className="ft"><button className="btn btn-a">Save attribute</button>
          {editing && <button type="button" className="btn" onClick={reset}>Cancel</button>}
          {err && <span className="err">{err}</span>}</div>
      </Panel>
    </form>

    <Panel title={`Attributes — ${list.data.length}`} bodyless>
      <Table head={['Code', 'Name', { label: 'Type', align: 'c' }, 'Permitted values',
        { label: 'Used on', align: 'c' }, '']} empty="No attributes yet.">
        {list.data.map(a => (
          <tr key={a.id}>
            <td className="mono"><b>{a.code}</b></td><td>{a.name}</td>
            <td className="c"><Tag>{TYPE_LABEL[a.attr_type]}</Tag></td>
            <td className="fine">{a.values.length ? a.values.join(', ') : '—'}</td>
            <td className="c mono">{a.used_on}</td>
            <td className="r">
              <button className="btn btn-sm" onClick={() => {
                setEditing(a.id); setF({ code: a.code, name: a.name, attr_type: a.attr_type })
                setValues(a.values); window.scrollTo({ top: 0, behavior: 'smooth' })
              }}>Edit</button>
              {!a.used_on && <button className="rm" onClick={async () => {
                try { await api.delAttribute(a.id); list.reload() }
                catch (x) { showFlash(x.message, 'bad') } }}>×</button>}
            </td></tr>))}
      </Table>
    </Panel>
  </>)
}
