import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { signUp, openTenants, forgotPassword, resetPassword } from '../lib/api'
import { Field, Alert } from '../components/ui'

const INDIAN_STATES = [
  ['01', 'Jammu and Kashmir'],
  ['02', 'Himachal Pradesh'],
  ['03', 'Punjab'],
  ['04', 'Chandigarh'],
  ['05', 'Uttarakhand'],
  ['06', 'Haryana'],
  ['07', 'Delhi'],
  ['08', 'Rajasthan'],
  ['09', 'Uttar Pradesh'],
  ['10', 'Bihar'],
  ['11', 'Sikkim'],
  ['12', 'Arunachal Pradesh'],
  ['13', 'Nagaland'],
  ['14', 'Manipur'],
  ['15', 'Mizoram'],
  ['16', 'Tripura'],
  ['17', 'Meghalaya'],
  ['18', 'Assam'],
  ['19', 'West Bengal'],
  ['20', 'Jharkhand'],
  ['21', 'Odisha'],
  ['22', 'Chhattisgarh'],
  ['23', 'Madhya Pradesh'],
  ['24', 'Gujarat'],
  ['25', 'Daman and Diu'],
  ['26', 'Dadra and Nagar Haveli and Daman and Diu'],
  ['27', 'Maharashtra'],
  ['28', 'Andhra Pradesh'],
  ['29', 'Karnataka'],
  ['30', 'Goa'],
  ['31', 'Lakshadweep'],
  ['32', 'Kerala'],
  ['33', 'Tamil Nadu'],
  ['34', 'Puducherry'],
  ['35', 'Andaman and Nicobar Islands'],
  ['36', 'Telangana'],
  ['37', 'Andhra Pradesh'],
  ['38', 'Ladakh'],
]

export default function Auth() {
  const { login, adopt } = useAuth()
  const [searchParams] = useSearchParams()
  const resetToken = searchParams.get('token')

  const [tab, setTab] = useState(resetToken ? 'reset' : 'in')
  const [err, setErr] = useState(null)
  const [ok, setOk] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tenants, setTenants] = useState([])
  const [f, setF] = useState({
  email: '',
  password: '',
  name: '',
  password2: '',
  mode: 'new',
  org_name: '',
  org_gstin: '',
  org_state: '',
  join_tenant_id: ''
})
  useEffect(() => { openTenants().then(setTenants).catch(() => {}) }, [])

  async function doSignIn(e) {  
    e.preventDefault(); setErr(null); setBusy(true)
    try { await login(f.email, f.password) }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  async function doSignUp(e) {
    e.preventDefault(); setErr(null); setOk(null)
    if (f.password !== f.password2) return setErr('The two passwords do not match')
    setBusy(true)
    try {
      const d = await signUp({ name: f.name, email: f.email, password: f.password,
        mode: f.mode, org_name: f.org_name, org_gstin: f.org_gstin || null,
        org_state: f.org_state, join_tenant_id: f.join_tenant_id ? Number(f.join_tenant_id) : null })
      if (d.status === 'active') adopt(d.token, d.tenant_id)
      else { setOk(d.message); setTab('in') }
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
    async function doForgot(e) {
    e.preventDefault()
    setErr(null)
    setOk(null)
    setBusy(true)

    try {
      const d = await forgotPassword(f.email)
      setOk(d.message)
    } catch (x) {
      setErr(x.message)
    } finally {
      setBusy(false)
    }
  }

  async function doReset(e) {
    e.preventDefault()
    setErr(null)
    setOk(null)

    if (!resetToken) {
      return setErr('This password reset link is invalid.')
    }

    if (f.password !== f.password2) {
      return setErr('The two passwords do not match')
    }

    setBusy(true)

    try {
      const d = await resetPassword(resetToken, f.password)
      setOk(d.message)
      set('password', '')
      set('password2', '')
      setTab('in')
      window.history.replaceState({}, '', '/')
    } catch (x) {
      setErr(x.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="center"><div className="authcard">
      <h2>Billing</h2>
      <p className="fine" style={{ margin: 0 }}>
        {tab === 'in' && 'Sign in to continue'}
        {tab === 'up' && 'Set up an organisation, or ask to join one'}
        {tab === 'forgot' && 'Recover access to your account'}
        {tab === 'reset' && 'Choose a new password'}
      </p>
      {(tab === 'in' || tab === 'up') && (
  <div className="tabs2">
    <button
      className={tab === 'in' ? 'on' : ''}
      onClick={() => { setTab('in'); setErr(null); setOk(null) }}
    >
      Sign in
    </button>

    <button
      className={tab === 'up' ? 'on' : ''}
      onClick={() => { setTab('up'); setErr(null); setOk(null) }}
    >
      Create an account
    </button>
  </div>
)}

      {tab === 'in' ? (
        <form onSubmit={doSignIn}>
          <Field label="Email">
            <input value={f.email} onChange={e => set('email', e.target.value)}
              autoComplete="username" placeholder="name@company.com" /></Field>
          <div style={{ marginTop: 11 }}><Field label="Password">
  <input type="password" value={f.password} autoComplete="current-password"
    onChange={e => set('password', e.target.value)} /></Field></div>

<div style={{ textAlign: 'right', marginTop: 8 }}>
  <button
    type="button"
    className="link"
    onClick={() => {
      setTab('forgot')
      setErr(null)
      setOk(null)
    }}
  >
    Forgot password?
  </button>
</div>

<div className="ft"><button className="btn btn-a" style={{ width: '100%' }}
  disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></div>
        </form>
      ) : tab === 'up' ? (
        <form onSubmit={doSignUp}>
          <div className="row c2">
            <Field label="Full name">
              <input value={f.name} onChange={e => set('name', e.target.value)} /></Field>
            <Field label="Email">
              <input value={f.email} onChange={e => set('email', e.target.value)} /></Field>
          </div>
          <div className="row c2" style={{ marginTop: 11 }}>
            <Field label="Password" hint="At least 8 characters">
              <input type="password" value={f.password} autoComplete="new-password"
                onChange={e => set('password', e.target.value)} /></Field>
            <Field label="Confirm password">
              <input type="password" value={f.password2} autoComplete="new-password"
                onChange={e => set('password2', e.target.value)} /></Field>
          </div>
          <div style={{ marginTop: 11 }}><Field label="What would you like to do">
            <select value={f.mode} onChange={e => set('mode', e.target.value)}>
              <option value="new">Set up a new organisation — I will be its administrator</option>
              <option value="join">Join an organisation that already exists</option>
            </select></Field></div>
          {f.mode === 'new' ? (
            <>
              <div className="row c2" style={{ marginTop: 11 }}>
                <Field label="Organisation name">
                  <input
                    value={f.org_name}
                    onChange={e => set('org_name', e.target.value)}
                  />
                </Field>

                <Field label="State">
                  <select
                    value={f.org_state}
                    onChange={e => set('org_state', e.target.value)}
                    required
                  >
                    <option value="">— choose state —</option>
                    {INDIAN_STATES.map(([code, name]) => (
                      <option key={code} value={code}>
                        {name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              <div style={{ marginTop: 11 }}>
                <Field
                  label="GSTIN"
                  hint="Optional. If entered, its state code must match the selected state."
                >
                  <input
                    className="mono"
                    maxLength={15}
                    value={f.org_gstin}
                    onChange={e =>
                      set('org_gstin', e.target.value.toUpperCase())
                    }
                  />
                </Field>
              </div>
            </>
          ) : (
            <div style={{ marginTop: 11 }}>
              <Field label="Organisation"
                hint="An administrator there must approve you before you can sign in">
                <select value={f.join_tenant_id} onChange={e => set('join_tenant_id', e.target.value)}>
                  <option value="">— choose —</option>
                  {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select></Field>
            </div>
          )}
          <div className="ft"><button className="btn btn-a" style={{ width: '100%' }}
            disabled={busy}>{busy ? 'Working…' : 'Create account'}</button></div>
        </form>
      ) : tab === 'forgot' ? (
  <form onSubmit={doForgot}>
    <Field label="Email">
      <input
        type="email"
        value={f.email}
        onChange={e => set('email', e.target.value)}
        autoComplete="email"
        placeholder="name@company.com"
        required
      />
    </Field>

    <div className="ft">
      <button
        className="btn btn-a"
        style={{ width: '100%' }}
        disabled={busy}
      >
        {busy ? 'Sending…' : 'Send reset link'}
      </button>
    </div>

    <div style={{ textAlign: 'center', marginTop: 12 }}>
      <button
        type="button"
        className="link"
        onClick={() => {
          setTab('in')
          setErr(null)
          setOk(null)
        }}
      >
        Back to sign in
      </button>
    </div>
  </form>
) : (
  <form onSubmit={doReset}>
    <Field label="New password" hint="At least 8 characters">
      <input
        type="password"
        value={f.password}
        autoComplete="new-password"
        onChange={e => set('password', e.target.value)}
        required
      />
    </Field>

    <div style={{ marginTop: 11 }}>
      <Field label="Confirm password">
        <input
          type="password"
          value={f.password2}
          autoComplete="new-password"
          onChange={e => set('password2', e.target.value)}
          required
        />
      </Field>
    </div>

    <div className="ft">
      <button
        className="btn btn-a"
        style={{ width: '100%' }}
        disabled={busy}
      >
        {busy ? 'Resetting…' : 'Reset password'}
      </button>
    </div>
  </form>
)}

      {err && <Alert kind="bad">{err}</Alert>}
      {ok && <Alert kind="ok">{ok}</Alert>}
    </div></div>
  )
}
