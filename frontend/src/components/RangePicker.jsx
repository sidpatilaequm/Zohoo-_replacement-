import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { useLoad } from './ui'

/** The browser's own date, so "Today" means today where the user is. */
export const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const sel = { padding: '7px 10px', border: '1px solid var(--line2)', borderRadius: 7 }

// Used if the server's list cannot be loaded (for example, no Reports access).
const FALLBACK = [
  { key: 'this_month', name: 'This month', section: 'This year' },
  { key: 'custom', name: 'Custom dates', section: 'Custom' },
]

/** The preset date ranges with the dates each covers today, from the server,
 *  so quarters and years follow the organisation's financial year. */
export function useRanges() {
  const { api } = useAuth()
  const today = localToday()
  const r = useLoad(() => api.salesRanges(today).catch(() => FALLBACK), [today])
  return { today, list: r.data || FALLBACK, byKey: Object.fromEntries((r.data || FALLBACK).map(x => [x.key, x])) }
}

/**
 * Choose a period: This year (today, week, month, quarter, year), the previous
 * day/week/month/quarter, the same periods last year, or custom dates.
 *
 * value / onChange: { range, start?, end? }. Presets apply at once; custom
 * dates apply when the user selects Apply. With allowAll, "All dates" is
 * offered first (range 'all').
 */
export default function RangePicker({ value, onChange, ranges, allowAll = false }) {
  const [pick, setPick] = useState(value.range)
  const today = localToday()
  const [start, setStart] = useState(value.start || today.slice(0, 8) + '01')
  const [end, setEnd] = useState(value.end || today)
  // v5.0: when the screen sets a new value (the year at the top changed), show it
  useEffect(() => {
    setPick(value.range)
    if (value.start) setStart(value.start)
    if (value.end) setEnd(value.end)
  }, [value.range, value.start, value.end])

  const sections = []
  for (const r of ranges.list) {
    let s = sections.find(x => x.name === r.section)
    if (!s) sections.push(s = { name: r.section || '', items: [] })
    s.items.push(r)
  }

  const choose = k => {
    setPick(k)
    if (k !== 'custom') onChange({ range: k })
  }
  const bad = !start || !end || start > end
  const pending = pick === 'custom' && (value.range !== 'custom' || value.start !== start || value.end !== end)

  return (<>
    <select value={pick} onChange={e => choose(e.target.value)} style={sel} aria-label="Period">
      {allowAll && <option value="all">All dates</option>}
      {sections.map(s => s.name === 'Custom'
        ? s.items.map(r => <option key={r.key} value={r.key}>{r.name}…</option>)
        : <optgroup key={s.name} label={s.name}>
          {s.items.map(r => <option key={r.key} value={r.key}>{r.name}</option>)}</optgroup>)}
    </select>
    {pick === 'custom' && <>
      <input type="date" value={start} max={end || undefined} onChange={e => setStart(e.target.value)}
        style={sel} aria-label="Start date" />
      <span className="fine">to</span>
      <input type="date" value={end} min={start || undefined} onChange={e => setEnd(e.target.value)}
        style={sel} aria-label="End date" />
      <button type="button" className={`btn btn-sm${pending ? ' btn-a' : ''}`} disabled={bad}
        onClick={() => onChange({ range: 'custom', start, end })}>Apply</button>
    </>}
  </>)
}

/** The start and end dates a picker value stands for, or nulls for all dates. */
export function rangeDates(value, ranges) {
  if (value.range === 'all') return { start: null, end: null }
  if (value.range === 'custom') return { start: value.start, end: value.end }
  const r = ranges.byKey[value.range]
  return { start: r?.start || null, end: r?.end || null }
}
