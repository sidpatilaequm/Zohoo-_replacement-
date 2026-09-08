import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'

export default function Company() {
  const { api } = useAuth()
  const org = useLoad(() => api.org())
  const states = useLoad(() => api.states())
  const [f, setF] = useState(null)
  const [smtp, setSmtp] = useState(null)
  const [logo, setLogo] = useState(null)
  const [err, setErr] = useState(null)
  const [check, setCheck] = useState(null)
  const [flash, showFlash] = useFlash()
  const fileRef = useRef()

  useEffect(() => {
    if (!org.data) return
    const { smtp: s, logo: l, ...rest } = org.data
    setF(rest); setSmtp({ ...s, password: '' }); setLogo(l)
  }, [org.data])

  if (org.loading || states.loading || !f) return <Loading />
  if (org.error) return <ErrorBox>{org.error}</ErrorBox>
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))
  const setS = (k, v) => setSmtp(s => ({ ...s, [k]: v }))

  async function saveOrg(e) {
    e.preventDefault(); setErr(null)
    try {
      await api.saveOrg({ name: f.name, company_type: f.company_type,
        gstin: f.gstin || null, pan: f.pan || null,
        addr: f.addr, city: f.city, state_code: f.state_code, pin: f.pin,
        inv_prefix: f.inv_prefix, inv_seq: Number(f.inv_seq),
        po_prefix: f.po_prefix, po_seq: Number(f.po_seq), bank: f.bank })
      showFlash('Organisation saved.'); org.reload()
    } catch (x) { setErr(x.message) }
  }
  async function saveSmtp(e) {
    e.preventDefault(); setErr(null)
    try {
      await api.saveSmtp({ ...smtp, port: smtp.port ? Number(smtp.port) : null })
      showFlash('Mail settings saved.'); setCheck(null); org.reload()
    } catch (x) { setErr(x.message) }
  }
  function pickLogo(e) {
    const file = e.target.files?.[0]; if (!file) return
    if (file.size > 500 * 1024) return showFlash('That file is over 500 KB.', 'bad')
    const r = new FileReader()
    r.onload = async () => {
      try { await api.saveLogo(r.result); setLogo(r.result); showFlash('Logo updated.'); org.reload() }
      catch (x) { showFlash(x.message, 'bad') }
    }
    r.readAsDataURL(file); e.target.value = ''
  }

  const trading = f.company_type === 'TRADING'
  return (<>
    {flash}
    <form onSubmit={saveOrg}>
      <Panel title="Business type">
        <div className="row">
          <Field label="This organisation operates as" hint="Decides whether stock is tracked">
            <select value={f.company_type}
              onChange={e => set('company_type', e.target.value)}>
              <option value="NONTRADING">Non-trading — IT products and services</option>
              <option value="TRADING">Trading — buys and sells physical goods</option>
            </select></Field>
          <div className="f" style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="btn btn-a" style={{ width: '100%' }}>Save business type</button></div>
        </div>
        <Alert kind={trading ? 'ok' : 'warn'}>
          {trading
            ? <><b>Trading company.</b> The <b>Ordering</b> and <b>Inventory</b> menus are
                available. Stock comes in against a purchase order and goes out through a sales
                order, delivery and goods issue, held by batch where the material is batch managed.</>
            : <><b>Non-trading company — IT products and services.</b> The <b>Ordering</b> and
                <b> Inventory</b> menus are hidden, because there is no physical stock to move.
                Invoicing, purchasing and the GST returns work exactly as before, and materials
                still carry a quantity so licences and service units can be counted.</>}
        </Alert>
      </Panel>
    </form>
    <Panel title="Company logo">
      <div className="logobox">
        {logo ? <img src={logo} alt="Company logo" />
          : <div style={{ width: 76, height: 76, border: '1px solid var(--line)', borderRadius: 9,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--faint)', fontSize: 11 }}>none</div>}
        <div>
          <div style={{ fontWeight: 600, marginBottom: 3 }}>Logo for this organisation</div>
          <p className="fine" style={{ margin: '0 0 10px' }}>
            Shown in the sidebar and on printed documents. PNG or JPEG, square works best, under 500 KB.</p>
          <button className="btn btn-sm btn-a" onClick={() => fileRef.current.click()}>Upload logo</button>
          <button className="btn btn-sm" style={{ marginLeft: 8 }} onClick={async () => {
            try { await api.saveLogo(null); setLogo(null); org.reload() }
            catch (x) { showFlash(x.message, 'bad') } }}>Remove</button>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/svg+xml"
            style={{ display: 'none' }} onChange={pickLogo} />
        </div>
      </div>
    </Panel>

    <form onSubmit={saveSmtp}>
      <Panel title="Email and SMTP" right={
        org.data.smtp?.from_email && org.data.smtp?.host
          ? <span className="tag ok">configured — {org.data.smtp.from_email}</span>
          : <span className="tag no">not configured</span>}>
        <div className="row">
          <Field label="Send from name"><input value={smtp.from_name || ''}
            onChange={e => setS('from_name', e.target.value)} /></Field>
          <Field label="Send from address"><input value={smtp.from_email || ''}
            onChange={e => setS('from_email', e.target.value)} /></Field>
          <Field label="Reply to"><input value={smtp.reply_to || ''}
            onChange={e => setS('reply_to', e.target.value)} /></Field>
          <Field label="Copy every mail to"><input value={smtp.bcc || ''}
            onChange={e => setS('bcc', e.target.value)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="SMTP host"><input className="mono" value={smtp.host || ''}
            placeholder="smtp.office365.com" onChange={e => setS('host', e.target.value)} /></Field>
          <Field label="Port"><input className="mono" type="number" value={smtp.port || ''}
            placeholder="587" onChange={e => setS('port', e.target.value)} /></Field>
          <Field label="Encryption"><select value={smtp.encryption || 'STARTTLS'}
            onChange={e => setS('encryption', e.target.value)}>
            <option value="STARTTLS">STARTTLS — usually 587</option>
            <option value="SSL">SSL / TLS — usually 465</option>
            <option value="NONE">None — port 25, not recommended</option></select></Field>
          <Field label="Username"><input className="mono" value={smtp.username || ''}
            onChange={e => setS('username', e.target.value)} /></Field>
          <Field label="Password"
            hint={org.data.smtp?.password_set ? 'A password is stored. Leave blank to keep it.' : ''}>
            <input type="password" value={smtp.password || ''}
              onChange={e => setS('password', e.target.value)} /></Field>
        </div>
        <div className="ft">
          <button className="btn btn-a">Save mail settings</button>
          <button type="button" className="btn" onClick={async () => {
            try { setCheck(await api.checkSmtp()) } catch (x) { showFlash(x.message, 'bad') } }}>
            Check settings</button>
        </div>
        {check && <Alert kind={check.ok ? 'ok' : 'warn'}>
          {check.ok ? 'The settings look complete. ' : 'Check: ' + check.problems.join('; ') + '. '}
          {check.note}</Alert>}
        <Alert kind="warn"><b>The password is stored on the server and never sent back to the browser.</b>
          The API reads it when it sends mail; this screen can only replace it. Sending happens
          server-side because a browser cannot open an SMTP connection.</Alert>
      </Panel>
    </form>

    <form onSubmit={saveOrg}>
      <Panel title="Organisation details">
        <div className="row">
          <Field label="Legal name"><input value={f.name}
            onChange={e => set('name', e.target.value)} required /></Field>
          <Field label="GSTIN"><input className="mono" maxLength={15} value={f.gstin || ''}
            onChange={e => set('gstin', e.target.value.toUpperCase())} /></Field>
          <Field label="PAN"><input className="mono" maxLength={10} value={f.pan || ''}
            onChange={e => set('pan', e.target.value.toUpperCase())} /></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="Address"><input value={f.addr || ''}
            onChange={e => set('addr', e.target.value)} /></Field>
          <Field label="City"><input value={f.city || ''}
            onChange={e => set('city', e.target.value)} /></Field>
          <Field label="State"><select value={f.state_code}
            onChange={e => set('state_code', e.target.value)}>
            {states.data.map(s => <option key={s.code} value={s.code}>{s.code} — {s.name}</option>)}
          </select></Field>
          <Field label="PIN"><input className="mono" maxLength={6} value={f.pin || ''}
            onChange={e => set('pin', e.target.value)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="Invoice prefix"><input className="mono" value={f.inv_prefix}
            onChange={e => set('inv_prefix', e.target.value)} /></Field>
          <Field label="Next invoice number"><input className="mono" type="number" min="1"
            value={f.inv_seq} onChange={e => set('inv_seq', e.target.value)} /></Field>
          <Field label="PO prefix"><input className="mono" value={f.po_prefix}
            onChange={e => set('po_prefix', e.target.value)} /></Field>
          <Field label="Next PO number"><input className="mono" type="number" min="1"
            value={f.po_seq} onChange={e => set('po_seq', e.target.value)} /></Field>
          <Field label="Bank details for documents"><input value={f.bank || ''}
            onChange={e => set('bank', e.target.value)} /></Field>
        </div>
        <div className="ft"><button className="btn btn-a">Save organisation</button>
          {err && <span className="err">{err}</span>}</div>
      </Panel>
    </form>
  </>)
}
