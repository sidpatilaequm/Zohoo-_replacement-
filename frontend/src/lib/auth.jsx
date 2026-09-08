import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { makeApi, signIn as apiSignIn } from './api'

const KEY = 'aequm.session'
const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(KEY)) } catch { return null }
  })
  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(!!session)

  useEffect(() => {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session))
    else sessionStorage.removeItem(KEY)
  }, [session])

  const api = useMemo(
    () => (session ? makeApi(session.token, session.tenantId) : null),
    [session])

  // Confirm the token with the server rather than trusting what is in storage.
  useEffect(() => {
    let alive = true
    if (!api) { setMe(null); setLoading(false); return }
    setLoading(true)
    api.me()
      .then(d => { if (alive) setMe(d) })
      .catch(() => { if (alive) setSession(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [api])

  async function login(email, password) {
    const d = await apiSignIn(email, password)
    setSession({ token: d.token, tenantId: d.tenant_id })
  }
  function logout() { setSession(null); setMe(null) }
  function switchTenant(tenantId) { setSession(s => ({ ...s, tenantId })) }
  function adopt(token, tenantId) { setSession({ token, tenantId }) }

  const perms = useMemo(() => new Set(me?.perms || []), [me])
  const can = p => perms.has(p)

  return (
    <AuthCtx.Provider value={{ session, me, api, loading, login, logout,
                               switchTenant, adopt, can, perms }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => {
  const v = useContext(AuthCtx)
  if (!v) throw new Error('useAuth must be used inside AuthProvider')
  return v
}
