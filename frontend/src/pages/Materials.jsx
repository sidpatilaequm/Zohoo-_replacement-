import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr } from '../lib/fmt'

const BLANK = { code: '', descr: '', price: '', cost: '', hsn: '',
  uom: 'NOS', batch_managed: false, shelf_life_days: '0',
  sgst_pct: '9', cgst_pct: '9', igst_pct: '18' }

export default function Materials() {
  const { api, me } = useAuth()
  const list = useLoad(() => api.materials())
  const uoms = useLoad(() => api.uoms())
  const attrs = useLoad(() => api.attributes())
  const hsns = useLoad(() => api.hsn())
  const [av, setAv] = useState({})
  const [f, setF] = useState(BLANK)
  const [err, setErr] = useState(null)
  const [editing, setEditing] = useState(null)
  const trading = me?.tenant?.company_type === 'TRADING'   // batch / shelf life / stock only matter for goods
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))
  function edit(m) {
    setEditing(m.id)
    setF({ code: m.code, descr: m.descr, price: String(m.price), cost: String(m.cost ?? ''), hsn: m.hsn, uom: m.uom,
      batch_managed: m.batch_managed, shelf_life_days: String(m.shelf_life_days ?? 0),
      sgst_pct: String(m.sgst_pct), cgst_pct: String(m.cgst_pct), igst_pct: String(m.igst_pct) })
    setAv(Object.fromEntries(Object.entries(m.attributes || {}).map(([k, v]) => [k, v])))
    setErr(null); window.scrollTo({ top: 0 })
  }
  function cancelEdit() { setEditing(null); setF(BLANK); setAv({}); setErr(null) }
  const split = Number(f.sgst_pct) + Number(f.cgst_pct)
  const mismatch = Math.abs(split - Number(f.igst_pct)) > 0.005

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const body = { ...f, code: f.code || null, price: Number(f.price), cost: Number(f.cost || 0),
        batch_managed: trading ? f.batch_managed : false,
        shelf_life_days: trading ? Number(f.shelf_life_days || 0) : 0,
        sgst_pct: Number(f.sgst_pct), cgst_pct: Number(f.cgst_pct),
        igst_pct: Number(f.igst_pct), use_hsn_rates: false,
        attributes: Object.fromEntries(Object.entries(av)
          .filter(([, v]) => v !== '' && v !== undefined)) }
      if (editing) await api.editMaterial(editing, body); else await api.addMaterial(body)
      setEditing(null); setF(BLANK); setAv({}); list.reload()
      showFlash(editing ? 'Material updated.' : 'Material saved.')
    } catch (x) { setErr(x.message) }
  }
  if (list.loading || uoms.loading || attrs.loading || hsns.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <Panel title={editing ? `Edit material ${f.code}` : 'Add material'}
      right={editing && <button type="button" className="btn btn-sm" onClick={cancelEdit}>Cancel edit</button>}>
      <form onSubmit={save}>
        <div className="row">
          <Field label="Material code" hint="Left blank, one is allocated from the company prefix"><input className="mono" value={f.code}
            onChange={e => set('code', e.target.value.toUpperCase())} /></Field>
          <Field label="Description"><input value={f.descr}
            onChange={e => set('descr', e.target.value)} required /></Field>
          <Field label="Selling price"><input className="mono" type="number" step="0.01"
            value={f.price} onChange={e => set('price', e.target.value)} required /></Field>
          <Field label="Cost price" hint="Used on purchase orders"><input className="mono"
            type="number" step="0.01" value={f.cost}
            onChange={e => set('cost', e.target.value)} /></Field>
          {trading && <Field label="Batch managed" hint="Stock is held by batch number">
            <select value={f.batch_managed ? 'Y' : 'N'}
              onChange={e => set('batch_managed', e.target.value === 'Y')}>
              <option value="N">No</option><option value="Y">Yes</option></select></Field>}
          {trading && <Field label="Shelf life in days" hint="Expiry is manufacturing date plus this">
            <input className="mono" type="number" min="0" value={f.shelf_life_days}
              onChange={e => set('shelf_life_days', e.target.value)} /></Field>}
          <Field label="HSN / SAC"
            hint={hsns.data.length ? 'Choosing one fills the rates below' : 'No codes on file yet'}>
            <select value={f.hsn} required onChange={e => {
              const code = e.target.value
              const h = hsns.data.find(x => x.code === code)
              setF(s2 => ({ ...s2, hsn: code, ...(h ? { sgst_pct: String(h.sgst_pct),
                cgst_pct: String(h.cgst_pct), igst_pct: String(h.igst_pct) } : {}) }))
            }}>
              <option value="">— select —</option>
              {hsns.data.map(h => (
                <option key={h.id} value={h.code}>
                  {h.code} · {h.descr} · {h.igst_pct}%</option>))}
            </select></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="Unit of measure"><select value={f.uom}
            onChange={e => set('uom', e.target.value)}>
            {uoms.data.map(u => <option key={u.code} value={u.code}>{u.code}</option>)}</select></Field>
          <Field label="SGST %"><input className="mono" type="number" step="0.01"
            value={f.sgst_pct} onChange={e => set('sgst_pct', e.target.value)} /></Field>
          <Field label="CGST %"><input className="mono" type="number" step="0.01"
            value={f.cgst_pct} onChange={e => set('cgst_pct', e.target.value)} /></Field>
          <Field label="IGST %"><input className="mono" type="number" step="0.01"
            value={f.igst_pct} onChange={e => set('igst_pct', e.target.value)} /></Field>
        </div>
        {attrs.data.length > 0 && (<>
          <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase',
            color: 'var(--muted)', margin: '18px 0 8px', fontWeight: 500 }}>Attributes</h3>
          <div className="row">
            {attrs.data.map(a => {
              const v = av[a.id] ?? ''
              if (a.attr_type === 'LIST') return (
                <Field key={a.id} label={a.name}>
                  <select value={v} onChange={e => setAv({ ...av, [a.id]: e.target.value })}>
                    <option value="">— none —</option>
                    {a.values.map(x => <option key={x}>{x}</option>)}
                  </select></Field>)
              if (a.attr_type === 'MULTI') {
                const sel = v ? v.split(', ') : []
                return (<Field key={a.id} label={a.name}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {a.values.map(x => (
                      <label key={x} style={{ display: 'flex', alignItems: 'center', gap: 5,
                        fontSize: 12, border: '1px solid var(--line)', borderRadius: 6,
                        padding: '5px 8px', cursor: 'pointer', textTransform: 'none',
                        letterSpacing: 0, color: 'var(--text)' }}>
                        <input type="checkbox" checked={sel.includes(x)}
                          style={{ width: 14, height: 14 }}
                          onChange={e => {
                            const n = e.target.checked ? [...sel, x] : sel.filter(y => y !== x)
                            setAv({ ...av, [a.id]: n.join(', ') })
                          }} /> {x}</label>))}
                  </div></Field>)
              }
              const t = a.attr_type === 'NUM' ? 'number' : a.attr_type === 'DATE' ? 'date' : 'text'
              return (<Field key={a.id} label={a.name}>
                <input type={t} className={a.attr_type === 'NUM' ? 'mono' : ''} value={v}
                  onChange={e => setAv({ ...av, [a.id]: e.target.value })} /></Field>)
            })}
          </div>
        </>)}
        {f.hsn && hsns.data.some(h => h.code === f.hsn) && <Alert kind="ok">
          Rates filled from the <b>{f.hsn}</b> entry in the HSN and SAC master. Change them here
          only if this material genuinely differs; the master is the better place to fix a rate
          that is wrong for everything.</Alert>}
        {mismatch && <Alert kind="warn">SGST {f.sgst_pct}% plus CGST {f.cgst_pct}% is {split}%,
          which does not equal IGST {f.igst_pct}%. Intra-state charges the split, inter-state
          charges the integrated rate — they must come to the same thing.</Alert>}
        <div className="ft"><button className="btn btn-a" disabled={mismatch}>{editing ? 'Update material' : 'Save material'}</button>
          {err && <span className="err">{err}</span>}</div>
      </form>
    </Panel>

    <Panel title={`Materials — ${list.data.length}`} bodyless>
      <Table head={['Code', 'Description', { label: 'Selling', align: 'r' },
        { label: 'Cost', align: 'r' }, { label: 'Margin', align: 'r' }, 'HSN',
        ...(trading ? [{ label: 'Stock', align: 'r' }] : []), { label: 'UoM', align: 'c' },
        ...(trading ? [{ label: 'Batch', align: 'c' }, { label: 'Shelf life', align: 'r' }] : []), 'Attributes',
        { label: 'SGST', align: 'r' }, { label: 'CGST', align: 'r' },
        { label: 'IGST', align: 'r' }, '']} empty="No materials yet.">
        {list.data.map(m => {
          const mar = m.price ? ((m.price - m.cost) / m.price) * 100 : null
          return (<tr key={m.id}>
            <td className="mono"><b>{m.code}</b></td><td>{m.descr}</td>
            <td className="r mono">{inr(m.price)}</td>
            <td className="r mono">{m.cost ? inr(m.cost) : '—'}</td>
            <td className="r mono" style={mar !== null && mar < 0 ? { color: 'var(--red)' } : {}}>
              {mar === null ? '—' : mar.toFixed(1) + '%'}</td>
            <td className="mono">{m.hsn}</td>
            {trading && <td className="r mono">{m.stock_qty}</td>}<td className="c mono">{m.uom}</td>
            {trading && <td className="c">{m.batch_managed ? <Tag kind="warn">Yes</Tag> : <Tag>No</Tag>}</td>}
            {trading && <td className="r mono">{m.shelf_life_days ? m.shelf_life_days + ' d' : '—'}</td>}
            <td className="fine">{Object.entries(m.attributes || {})
              .map(([aid, val]) => {
                const a = attrs.data.find(x => String(x.id) === String(aid))
                return a ? `${a.name}: ${val}` : null
              }).filter(Boolean).join(' · ') || '—'}</td>
            <td className="r mono">{m.sgst_pct}%</td><td className="r mono">{m.cgst_pct}%</td>
            <td className="r mono">{m.igst_pct}%</td>
            <td className="r" style={{ whiteSpace: 'nowrap' }}>
              <button className="btn btn-sm" onClick={() => edit(m)}>Edit</button>
              <button className="rm" style={{ marginLeft: 4 }} onClick={async () => {
              try { await api.delMaterial(m.id); list.reload() }
              catch (x) { showFlash(x.message, 'bad') } }}>×</button></td>
          </tr>)})}
      </Table>
    </Panel>
  </>)
}
