import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'

/** Directors' signature images. Up to two are ticked to print in the
 *  Authorised Signatory block of tax and proforma invoices. */
const DESIGNATIONS = ['Director', 'Managing Director', 'Whole-time Director',
  'Partner', 'Proprietor', 'Authorised Signatory']
const MAX_BYTES = 3 * 1024 * 1024

function readImage(file) {
  return new Promise((res, rej) => {
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) return rej(new Error('Use a PNG, JPEG or WebP image.'))
    if (file.size > MAX_BYTES) return rej(new Error('That image is over 3 MB.'))
    const r = new FileReader()
    r.onload = () => res(r.result)
    r.onerror = () => rej(new Error('Could not read that file.'))
    r.readAsDataURL(file)
  })
}

function SigCard({ s, printedCount, max, onSaved, onError }) {
  const { api } = useAuth()
  const [edit, setEdit] = useState(null)
  const [busy, setBusy] = useState(false)
  const [on, setOn] = useState(s.on_invoices)
  useEffect(() => setOn(s.on_invoices), [s.on_invoices])
  const fileRef = useRef()
  const save = async (patch) => {
    setBusy(true)
    if ('on_invoices' in patch) setOn(patch.on_invoices)          // show it at once
    try { await api.editSignatory(s.id, { name: s.name, designation: s.designation,
      on_invoices: s.on_invoices, ...patch }); onSaved() }
    catch (x) { setOn(s.on_invoices); onError(x.message) } finally { setBusy(false) }
  }
  const blocked = !on && printedCount >= max
  return (<div className={`sig-card${on ? ' on' : ''}`}>
    <div className="sig-paper"><img src={s.image} alt={`Signature of ${s.name}`} /></div>
    {edit ? <div className="sig-edit">
      <input value={edit.name} aria-label="Name" maxLength={120}
        onChange={e => setEdit({ ...edit, name: e.target.value })} />
      <input value={edit.designation} aria-label="Designation" list="sig-desig" maxLength={80}
        onChange={e => setEdit({ ...edit, designation: e.target.value })} />
      <div className="ft" style={{ marginTop: 6 }}>
        <button className="btn btn-sm btn-a" disabled={busy || !edit.name.trim()}
          onClick={async () => { await save(edit); setEdit(null) }}>Save</button>
        <button className="btn btn-sm" onClick={() => setEdit(null)}>Cancel</button></div>
    </div> : <div className="sig-who"><b>{s.name}</b><span>{s.designation}</span></div>}
    <label className={`sig-toggle${blocked ? ' dim' : ''}`}
      title={blocked ? `Two signatures already print. Untick one first.` : ''}>
      <input type="checkbox" checked={on} disabled={busy || blocked}
        onChange={e => save({ on_invoices: e.target.checked })} />
      Signs invoices</label>
    <div className="sig-actions">
      {!edit && <button className="btn btn-sm" onClick={() => setEdit({ name: s.name, designation: s.designation })}>Edit</button>}
      <button className="btn btn-sm" disabled={busy} onClick={() => fileRef.current.click()}>Replace image</button>
      <button className="btn btn-sm" style={{ color: 'var(--red)' }} disabled={busy} onClick={async () => {
        if (!window.confirm(`Remove ${s.name}'s signature? Invoices printed from now on will not carry it.`)) return
        try { await api.delSignatory(s.id); onSaved() } catch (x) { onError(x.message) } }}>Remove</button>
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" style={{ display: 'none' }}
        onChange={async e => { const f = e.target.files?.[0]; e.target.value = ''
          if (!f) return
          try { await save({ image: await readImage(f) }) } catch (x) { onError(x.message) } }} />
    </div>
    <div className="fine">Uploaded {s.uploaded_by ? `by ${s.uploaded_by} ` : ''}
      {s.uploaded_at ? `on ${new Date(s.uploaded_at).toLocaleDateString('en-IN', { dateStyle: 'medium' })}` : ''}</div>
  </div>)
}

export default function Signatures() {
  const { api, me } = useAuth()
  const data = useLoad(() => api.signatories())
  const [flash, showFlash] = useFlash()
  const [f, setF] = useState({ name: '', designation: 'Director', image: null, on_invoices: true })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [settings, setSettings] = useState(null)
  const fileRef = useRef()
  useEffect(() => { if (data.data) setSettings(data.data.settings) }, [data.data])

  if (!data.data && data.loading) return <Loading />
  if (!data.data && data.error) return <ErrorBox>{data.error}</ErrorBox>
  if (!settings) return <Loading />
  const { signatories: list, max_printed: max } = data.data
  const printed = list.filter(s => s.on_invoices)
  const org = me?.tenant?.name || 'the company'

  async function add(e) {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const s = await api.addSignatory({ ...f, on_invoices: f.on_invoices && printed.length < max })
      showFlash(`${s.name}'s signature added${s.on_invoices ? ' and will print on invoices' : ''}.`)
      setF({ name: '', designation: 'Director', image: null, on_invoices: true }); data.reload()
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  async function setting(k, v) {
    const before = settings
    setSettings({ ...settings, [k]: v })
    try { await api.sigSettings({ ...before, [k]: v }) }
    catch (x) { setSettings(before); showFlash(x.message, 'bad') }
  }

  return (<>
    {flash}
    <datalist id="sig-desig">{DESIGNATIONS.map(d => <option key={d} value={d} />)}</datalist>

    <Panel title="Where the signatures print">
      <div className="sig-layout">
        <div>
          <p style={{ margin: '0 0 10px' }}>Tick <b>Signs invoices</b> on one director, or on both, and
            their signature prints in the signatory block of every invoice, with their name and designation
            under it. It also goes out on invoices sent by e-mail.</p>
          <label className="sig-toggle"><input type="checkbox" checked={settings.sig_on_tax}
            onChange={e => setting('sig_on_tax', e.target.checked)} /> Print on tax invoices</label>
          <label className="sig-toggle"><input type="checkbox" checked={settings.sig_on_pro}
            onChange={e => setting('sig_on_pro', e.target.checked)} /> Print on proforma invoices</label>
          <p className="fine" style={{ margin: '10px 0 0' }}>This is an image of a signature, not a Digital
            Signature Certificate (DSC): the PDF is not cryptographically signed.</p>
        </div>
        <div className="sig-preview" aria-label="How the signatory block will print">
          <div className="fine">On the invoice</div>
          <div className="sig-preview-for">For {org}</div>
          {printed.length ? <div className="sig-preview-row">{printed.map(s => (
            <div key={s.id}><img src={s.image} alt="" /><div>{s.name}</div><div className="fine">{s.designation}</div></div>))}
          </div> : <div className="sig-preview-blank">left blank to sign by hand</div>}
          <div>{printed.length > 1 ? 'Authorized Signatories' : 'Authorized Signature'}</div>
          {!settings.sig_on_tax && !settings.sig_on_pro && printed.length > 0 &&
            <Alert kind="warn">Both switches are off, so no invoice carries a signature.</Alert>}
        </div>
      </div>
    </Panel>

    <Panel title={`Directors — ${list.length}`} bodyless>
      {list.length ? <div className="sig-grid">
        {list.map(s => <SigCard key={s.id} s={s} printedCount={printed.length} max={max}
          onSaved={data.reload} onError={m => showFlash(m, 'bad')} />)}</div>
        : <div className="panel-bd fine">No signatures yet. Add the first director below.</div>}
    </Panel>

    <form onSubmit={add}>
      <Panel title="Add a director's signature">
        <div className="sig-add">
          <div>
            <div className="row">
              <Field label="Name as it should print"><input value={f.name} required maxLength={120}
                onChange={e => setF({ ...f, name: e.target.value })} placeholder="e.g. Alok Sharma" /></Field>
              <Field label="Designation"><input value={f.designation} list="sig-desig" required maxLength={80}
                onChange={e => setF({ ...f, designation: e.target.value })} /></Field>
            </div>
            <label className={`sig-toggle${printed.length >= max ? ' dim' : ''}`} style={{ marginTop: 12 }}>
              <input type="checkbox" checked={f.on_invoices && printed.length < max} disabled={printed.length >= max}
                onChange={e => setF({ ...f, on_invoices: e.target.checked })} />
              Signs invoices{printed.length >= max ? ' (two already do; untick one to add a third)' : ''}</label>
            <p className="fine" style={{ margin: '10px 0 0' }}>Sign in dark ink on plain white paper and take a
              photo in good light, or scan it. PNG, JPEG or WebP, up to 3 MB. The paper is made transparent and
              the image trimmed to the signature when you save.</p>
          </div>
          <button type="button" className={`sig-drop${f.image ? ' has' : ''}`} onClick={() => fileRef.current.click()}>
            {f.image ? <img src={f.image} alt="Chosen signature" /> : <span>Choose signature image</span>}
          </button>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" style={{ display: 'none' }}
            onChange={async e => { const file = e.target.files?.[0]; e.target.value = ''
              if (!file) return
              try { setErr(null); setF(s => ({ ...s, image: null })); const img = await readImage(file); setF(s => ({ ...s, image: img })) }
              catch (x) { setErr(x.message) } }} />
        </div>
        <div className="ft">
          <button className="btn btn-a" disabled={busy || !f.image || !f.name.trim()}>
            {busy ? 'Saving…' : 'Save signature'}</button>
          {err && <span className="err">{err}</span>}
        </div>
      </Panel>
    </form>
  </>)
}
