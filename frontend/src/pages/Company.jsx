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
        po_prefix: f.po_prefix, po_seq: Number(f.po_seq), bank: f.bank || null,
        inv_fy: !!f.inv_fy, po_fy: !!f.po_fy, vinv_prefix: f.vinv_prefix || 'PINV/',
        vinv_seq: Number(f.vinv_seq || 1), vinv_fy: !!f.vinv_fy,
        fy_start_month: Number(f.fy_start_month || 4), fy_start_day: Number(f.fy_start_day || 1),
        cust_prefix: f.cust_prefix || 'C', cust_seq: Number(f.cust_seq || 1),
        vend_prefix: f.vend_prefix || 'V', vend_seq: Number(f.vend_seq || 1),
        mat_prefix: f.mat_prefix || 'M', mat_seq: Number(f.mat_seq || 1),
        bank_name: f.bank_name || null, bank_ifsc: (f.bank_ifsc || '').toUpperCase() || null,
        bank_account: f.bank_account || null })
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
  const pad = (pre, n) => `${pre}${String(Number(n || 1)).padStart(3, '0')}`
  const fyEnd = (m, d) => { const mm = Number(m || 4), dd = Number(d || 1)
    const e = new Date(2027, mm - 1, dd); e.setDate(e.getDate() - 1)
    return `${e.getDate()} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][e.getMonth()]}` }
  const preview = (pre, fy, n) => fy ? `${pre}${org.data.current_fy || '2026-27'}/001` : pad(pre, n)
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
        <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--muted)',
          margin: '18px 0 8px', fontWeight: 500 }}>Financial year</h3>
        <div className="row">
          <Field label="Year starts on" hint="Indian default 1 April; 1 January gives a calendar year">
            <div style={{ display: 'flex', gap: 6 }}>
              <input className="mono" type="number" min="1" max="31" style={{ width: 70 }} value={f.fy_start_day ?? 1}
                onChange={e => set('fy_start_day', e.target.value)} />
              <select value={f.fy_start_month ?? 4} onChange={e => set('fy_start_month', e.target.value)}>
                {['January','February','March','April','May','June','July','August','September','October','November','December'].map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select></div></Field>
          <Field label="Year ends on" hint="Always the day before the next start">
            <input readOnly className="mono" value={fyEnd(f.fy_start_month, f.fy_start_day)} /></Field>
          <Field label="Current financial year" hint="Registers and reports default to this">
            <input readOnly className="mono" value={org.data.current_fy || ''} /></Field>
        </div>

        <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--muted)',
          margin: '18px 0 8px', fontWeight: 500 }}>Number ranges</h3>
        <p className="fine" style={{ margin: '0 0 8px' }}>Tick "with financial year" to put the year in the number and restart
          the count every year — e.g. <span className="mono">INV/2026-27/001</span>. Untick for one running number.</p>
        <div className="row">
          <Field label="Invoice prefix"><input className="mono" value={f.inv_prefix}
            onChange={e => set('inv_prefix', e.target.value)} /></Field>
          <Field label="Next invoice number" hint={f.inv_fy ? 'Per year; managed automatically' : ''}>
            <input className="mono" type="number" min="1" disabled={!!f.inv_fy}
              value={f.inv_seq} onChange={e => set('inv_seq', e.target.value)} /></Field>
          <Field label="With financial year"><select value={f.inv_fy ? 'Y' : 'N'}
            onChange={e => set('inv_fy', e.target.value === 'Y')}><option value="N">No</option><option value="Y">Yes</option></select></Field>
          <Field label="Preview"><input readOnly className="mono" value={preview(f.inv_prefix, f.inv_fy, f.inv_seq)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <Field label="PO prefix"><input className="mono" value={f.po_prefix}
            onChange={e => set('po_prefix', e.target.value)} /></Field>
          <Field label="Next PO number"><input className="mono" type="number" min="1" disabled={!!f.po_fy}
            value={f.po_seq} onChange={e => set('po_seq', e.target.value)} /></Field>
          <Field label="With financial year"><select value={f.po_fy ? 'Y' : 'N'}
            onChange={e => set('po_fy', e.target.value === 'Y')}><option value="N">No</option><option value="Y">Yes</option></select></Field>
          <Field label="Preview"><input readOnly className="mono" value={preview(f.po_prefix, f.po_fy, f.po_seq)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <Field label="Purchase invoice prefix" hint="Our own number for a vendor's invoice"><input className="mono" value={f.vinv_prefix || 'PINV/'}
            onChange={e => set('vinv_prefix', e.target.value)} /></Field>
          <Field label="Next purchase invoice number"><input className="mono" type="number" min="1" disabled={!!f.vinv_fy}
            value={f.vinv_seq ?? 1} onChange={e => set('vinv_seq', e.target.value)} /></Field>
          <Field label="With financial year"><select value={f.vinv_fy ? 'Y' : 'N'}
            onChange={e => set('vinv_fy', e.target.value === 'Y')}><option value="N">No</option><option value="Y">Yes</option></select></Field>
          <Field label="Preview"><input readOnly className="mono" value={preview(f.vinv_prefix || 'PINV/', f.vinv_fy, f.vinv_seq ?? 1)} /></Field>
        </div>

        <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--muted)',
          margin: '18px 0 8px', fontWeight: 500 }}>Automatic codes for masters</h3>
        <p className="fine" style={{ margin: '0 0 8px' }}>A customer, vendor or material saved without a code gets the next one from here.</p>
        <div className="row">
          <Field label="Customer code prefix"><input className="mono" value={f.cust_prefix ?? 'C'}
            onChange={e => set('cust_prefix', e.target.value)} /></Field>
          <Field label="Next customer"><input className="mono" type="number" min="1" value={f.cust_seq ?? 1}
            onChange={e => set('cust_seq', e.target.value)} /></Field>
          <Field label="Vendor code prefix"><input className="mono" value={f.vend_prefix ?? 'V'}
            onChange={e => set('vend_prefix', e.target.value)} /></Field>
          <Field label="Next vendor"><input className="mono" type="number" min="1" value={f.vend_seq ?? 1}
            onChange={e => set('vend_seq', e.target.value)} /></Field>
          <Field label="Material code prefix"><input className="mono" value={f.mat_prefix ?? 'M'}
            onChange={e => set('mat_prefix', e.target.value)} /></Field>
          <Field label="Next material"><input className="mono" type="number" min="1" value={f.mat_seq ?? 1}
            onChange={e => set('mat_seq', e.target.value)} /></Field>
        </div>
        <p className="fine" style={{ margin: '6px 0 0' }}>Next codes: <span className="mono">{pad(f.cust_prefix ?? 'C', f.cust_seq)}</span> ·{' '}
          <span className="mono">{pad(f.vend_prefix ?? 'V', f.vend_seq)}</span> · <span className="mono">{pad(f.mat_prefix ?? 'M', f.mat_seq)}</span></p>

        <h3 style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--muted)',
          margin: '18px 0 8px', fontWeight: 500 }}>Bank details — printed on customer invoices</h3>
        <div className="row">
          <Field label="Bank name"><input value={f.bank_name || ''} placeholder="e.g. SBI"
            onChange={e => set('bank_name', e.target.value)} /></Field>
          <Field label="IFSC code" hint="Eleven characters, e.g. SBIN0040807"><input className="mono" maxLength={11}
            value={f.bank_ifsc || ''} onChange={e => set('bank_ifsc', e.target.value.toUpperCase())} /></Field>
          <Field label="Account number"><input className="mono" value={f.bank_account || ''}
            onChange={e => set('bank_account', e.target.value)} /></Field>
        </div>
        <p className="fine" style={{ margin: '6px 0 0' }}>Prints under Terms &amp; Conditions as
          "{f.name}, {f.bank_name || 'Bank'} Account No: {f.bank_account || '…'} IFSC Code: {f.bank_ifsc || '…'}".</p>
        <div className="ft"><button className="btn btn-a">Save organisation</button>
          {err && <span className="err">{err}</span>}</div>
      </Panel>
    </form>
  </>)
}
