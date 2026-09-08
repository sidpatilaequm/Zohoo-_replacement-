import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'

const BLANK = { code: '', descr: '', kind: 'HSN', sgst_pct: '9', cgst_pct: '9',
  igst_pct: '18', cess_pct: '0' }

export default function HsnCodes() {
  const { api } = useAuth()
  const list = useLoad(() => api.hsn())
  const [f, setF] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [err, setErr] = useState(null)
  const [flash, showFlash] = useFlash()
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))
  const split = Number(f.sgst_pct) + Number(f.cgst_pct)
  const mismatch = Math.abs(split - Number(f.igst_pct)) > 0.005

  async function save(e) {
    e.preventDefault(); setErr(null)
    try {
      const body = { ...f, sgst_pct: Number(f.sgst_pct), cgst_pct: Number(f.cgst_pct),
        igst_pct: Number(f.igst_pct), cess_pct: Number(f.cess_pct || 0) }
      if (editing) await api.editHsn(editing, body); else await api.addHsn(body)
      setF(BLANK); setEditing(null); list.reload(); showFlash('Code saved.')
    } catch (x) { setErr(x.message) }
  }
  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  return (<>
    {flash}
    <Alert kind="ok"><b>Rates kept here default onto a material.</b> Enter the code once with its
      GST rate, and any material carrying that HSN or SAC picks the rate up automatically. A
      material can still override it if a particular line genuinely differs.</Alert>

    <form onSubmit={save}>
      <Panel title={editing ? 'Edit code' : 'Add HSN or SAC code'}>
        <div className="row">
          <Field label="Code"><input className="mono" maxLength={8} value={f.code} required
            onChange={e => set('code', e.target.value)} /></Field>
          <Field label="Description"><input value={f.descr} required
            onChange={e => set('descr', e.target.value)} /></Field>
          <Field label="Kind" hint="HSN for goods, SAC for services">
            <select value={f.kind} onChange={e => set('kind', e.target.value)}>
              <option value="HSN">HSN — goods</option>
              <option value="SAC">SAC — services</option></select></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="SGST %"><input className="mono" type="number" step="0.01"
            value={f.sgst_pct} onChange={e => set('sgst_pct', e.target.value)} /></Field>
          <Field label="CGST %"><input className="mono" type="number" step="0.01"
            value={f.cgst_pct} onChange={e => set('cgst_pct', e.target.value)} /></Field>
          <Field label="IGST %"><input className="mono" type="number" step="0.01"
            value={f.igst_pct} onChange={e => set('igst_pct', e.target.value)} /></Field>
          <Field label="Cess %" hint="Leave at zero unless cess applies">
            <input className="mono" type="number" step="0.01" value={f.cess_pct}
              onChange={e => set('cess_pct', e.target.value)} /></Field>
        </div>
        {mismatch && <Alert kind="warn">SGST {f.sgst_pct}% plus CGST {f.cgst_pct}% is {split}%,
          which does not equal IGST {f.igst_pct}%. Intra-state charges the split and inter-state
          the integrated rate, so they must come to the same thing.</Alert>}
        <div className="ft"><button className="btn btn-a" disabled={mismatch}>Save code</button>
          {editing && <button type="button" className="btn"
            onClick={() => { setF(BLANK); setEditing(null) }}>Cancel</button>}
          {err && <span className="err">{err}</span>}</div>
      </Panel>
    </form>

    <Panel title={`HSN and SAC codes — ${list.data.length}`} bodyless>
      <Table head={['Code', { label: 'Kind', align: 'c' }, 'Description',
        { label: 'SGST', align: 'r' }, { label: 'CGST', align: 'r' },
        { label: 'IGST', align: 'r' }, { label: 'Cess', align: 'r' },
        { label: 'Materials', align: 'c' }, '']} empty="No codes yet.">
        {list.data.map(h => (
          <tr key={h.id}>
            <td className="mono"><b>{h.code}</b></td>
            <td className="c"><Tag kind={h.kind === 'SAC' ? 'warn' : 'ok'}>{h.kind}</Tag></td>
            <td>{h.descr}</td>
            <td className="r mono">{h.sgst_pct}%</td><td className="r mono">{h.cgst_pct}%</td>
            <td className="r mono"><b>{h.igst_pct}%</b></td>
            <td className="r mono">{h.cess_pct ? h.cess_pct + '%' : '—'}</td>
            <td className="c mono">{h.used_on}</td>
            <td className="r">
              <button className="btn btn-sm" onClick={() => {
                setEditing(h.id); setF({ code: h.code, descr: h.descr, kind: h.kind,
                  sgst_pct: h.sgst_pct, cgst_pct: h.cgst_pct, igst_pct: h.igst_pct,
                  cess_pct: h.cess_pct })
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}>Edit</button>
              {!h.used_on && <button className="rm" onClick={async () => {
                try { await api.delHsn(h.id); list.reload() }
                catch (x) { showFlash(x.message, 'bad') } }}>×</button>}
            </td></tr>))}
      </Table>
    </Panel>
  </>)
}
