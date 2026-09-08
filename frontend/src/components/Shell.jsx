import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { MENU, TRADING_ONLY } from '../lib/menu'
import { initials } from '../lib/fmt'

export default function Shell({ children }) {
  const { me, can, logout, switchTenant, session } = useAuth()
  const loc = useLocation()
  const tenant = me?.tenant
  const tenants = me?.tenants || []
  const current = tenants.find(t => t.id === session?.tenantId)
  // Ordering and Inventory only make sense for a trading business
  const trading = tenant?.company_type === 'TRADING'
  const visible = MENU
    .map(g => ({ ...g, items: g.items.filter(i =>
      can(i.key) && !(TRADING_ONLY.has(i.key) && !trading)) }))
    .filter(g => g.items.length)
  const title = MENU.flatMap(g => g.items)
    .find(i => loc.pathname.startsWith(i.path))?.label || ''

  return (
    <div className="app">
      <nav className="side">
        <div className="brand">
          {tenant?.logo
            ? <img src={tenant.logo} alt="" />
            : <div className="ph">{initials(tenant?.name || '?')}</div>}
          <div><div className="nm">{tenant?.name}</div><div className="sub">Billing</div></div>
        </div>
        {visible.map(g => (
          <div key={g.group}>
            <div className="grp">{g.group}</div>
            {g.items.map(i => (
              <NavLink key={i.key} to={i.path}
                className={({ isActive }) => 'mi' + (isActive ? ' on' : '')}>
                {i.label}
              </NavLink>))}
          </div>))}
        <div className="foot">{me?.user?.name}<br />
          <span style={{ fontSize: 10.5 }}>{current?.group}</span></div>
      </nav>
      <div className="main">
        <div className="topbar">
          <h1>{title}</h1>
          <div className="sp">
            <select className="tsel" value={session?.tenantId || ''}
              disabled={tenants.length < 2}
              onChange={e => switchTenant(Number(e.target.value))}>
              {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <div className="uchip">
              <span className="av">{initials(me?.user?.name || '')}</span>
              <span>{me?.user?.name}<br />
                <span className="rl">{current?.group}</span></span>
            </div>
            <button className="btn btn-sm" onClick={logout}>Sign out</button>
          </div>
        </div>
        <div className="wrap">{children}</div>
      </div>
    </div>
  )
}
