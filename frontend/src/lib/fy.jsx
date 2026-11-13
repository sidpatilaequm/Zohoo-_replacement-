import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useAuth } from './auth'

/* v5.0 — one financial year for the whole app.
 *
 * The top bar holds the year every screen opens on: the current financial
 * year (2026-27 from 1 April 2026), following the company's own year start
 * (Company profile). Screens with their own year or period picker start on
 * it; registers and lists without one show that year's documents. Changing
 * it in the top bar changes every screen; "All years" shows everything.
 * The choice lasts for the browser tab, so a new session starts on the
 * current year again. */

const FyCtx = createContext(null)

// Before the list loads (or if it cannot): the Indian default, 1 April.
function fallbackYears(today = new Date()) {
  const y = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1
  const label = `${y}-${String(y + 1).slice(-2)}`
  return [{ label, current: true, start: `${y}-04-01`, end: `${y + 1}-03-31` }]
}

const isoDate = v => (v ? String(v).slice(0, 10) : '')

export function FyProvider({ children }) {
  const { api, session } = useAuth()
  const key = `aequm.fy.${session?.tenantId || ''}`
  const [years, setYears] = useState(null)
  const [fy, setFyState] = useState(() => sessionStorage.getItem(key))

  useEffect(() => {
    if (!session?.token) return
    let live = true
    api.financialYears()
      .then(ys => (Array.isArray(ys) && ys.length && typeof ys[0] === 'object' ? ys : fallbackYears()))
      .catch(() => fallbackYears())
      .then(ys => {
        if (!live) return
        setYears(ys)
        const saved = sessionStorage.getItem(key)
        const pick = saved === 'ALL' ? 'ALL'
          : (ys.find(y => y.label === saved) || ys.find(y => y.current) || ys[0]).label
        setFyState(pick)
      })
    return () => { live = false }
  }, [session?.tenantId, session?.token]) // eslint-disable-line

  const value = useMemo(() => {
    const list = years || fallbackYears()
    const label = fy && fy !== 'ALL' ? fy : (fy === 'ALL' ? '' : (list.find(y => y.current) || list[0]).label)
    const info = list.find(y => y.label === label)
    return {
      ready: years !== null,
      years: list,
      fy: label,                                  // '' when "All years"
      current: (list.find(y => y.current) || list[0]).label,
      param: label ? `FY${label}` : '',           // what the API's period / financial_year takes
      name: label ? `FY ${label}` : 'all years',
      setFy: l => { const v = l || 'ALL'; setFyState(v); sessionStorage.setItem(key, v) },
      /** Is this date in the selected year? Always true for "All years". */
      inFy: d => !info || (!!d && isoDate(d) >= info.start && isoDate(d) <= info.end),
    }
  }, [years, fy, key])

  return <FyCtx.Provider value={value}>{children}</FyCtx.Provider>
}

export function useFy() {
  const v = useContext(FyCtx)
  if (v) return v
  const list = fallbackYears()
  return { ready: true, years: list, fy: list[0].label, current: list[0].label, param: `FY${list[0].label}`,
           name: `FY ${list[0].label}`, setFy: () => {}, inFy: () => true }
}

/** The year selector in the top bar. */
export function TopFyPicker() {
  const { years, fy, setFy } = useFy()
  return (
    <select className="tsel" aria-label="Financial year" value={fy || ''} title="The financial year every screen shows"
      onChange={e => setFy(e.target.value)}>
      {years.map(y => <option key={y.label} value={y.label}>FY {y.label}{y.current ? ' (current)' : ''}</option>)}
      <option value="">All years</option>
    </select>)
}

/** A document's date, whatever the list calls it. */
export const rowDate = r => r.pay_date || r.doc_date || r.count_date || r.grn_date || r.date || r.txn_date || r.created_at

/** Rows of a list that fall in the selected year. */
export function useFyRows() {
  const { inFy } = useFy()
  return rows => (rows || []).filter(r => inFy(rowDate(r)))
}

/** "in FY 2026-27" after a list's count, saying how many are in other years. */
export function FyCount({ shown, total }) {
  const { name, fy } = useFy()
  return <span>{shown} in {name}{fy && total > shown
    ? <span className="fine"> · {total - shown} in other years (choose All years at the top)</span> : null}</span>
}

/** The date range a range-picker screen opens on (v5.0): "This year" (the
 *  financial year to date) for the current year, that year's dates for an
 *  earlier one, all dates for "All years". `key` changes when the year does. */
export function useFyRange() {
  const { fy, current, years } = useFy()
  return useMemo(() => {
    if (!fy) return { key: 'all', range: 'all' }
    if (fy === current) return { key: fy, range: 'this_year' }
    const y = years.find(x => x.label === fy)
    return { key: fy, range: 'custom', start: y?.start, end: y?.end }
  }, [fy, current, years])
}
