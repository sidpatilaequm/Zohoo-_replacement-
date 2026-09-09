import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'

export const Panel = ({ title, right, children, bodyless }) => (
  <div className="panel">
    {(title || right) && (
      <div className="panel-hd">{title && <h2>{title}</h2>}
        {right && <div style={{ marginLeft: 'auto', display: 'flex', gap: 8,
          alignItems: 'center', flexWrap: 'wrap' }}>{right}</div>}</div>)}
    {bodyless ? children : <div className="panel-bd">{children}</div>}
  </div>
)

export const Field = ({ label, hint, children }) => (
  <div className="f"><label>{label}</label>{children}
    {hint && <div className="hint">{hint}</div>}</div>
)

export const Alert = ({ kind = 'ok', children }) =>
  <div className={`alert ${kind}`}>{children}</div>

export const Tag = ({ kind = 'no', children }) =>
  <span className={`tag ${kind}`}>{children}</span>

export const Table = ({ head, children, empty, cols }) => (
  <div className="scroll"><table>
    <thead><tr>{head.map((h, i) =>
      <th key={i} className={h.align || ''}>{h.label ?? h}</th>)}</tr></thead>
    <tbody>{children && children.length
      ? children
      : <tr><td colSpan={cols || head.length}
          style={{ textAlign: 'center', padding: 24, color: 'var(--faint)' }}>
          {empty || 'Nothing to show.'}</td></tr>}</tbody>
  </table></div>
)

/** Loads once, exposes {data, error, loading, reload}. */
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [n, setN] = useState(0)
  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.resolve(fn())
      .then(d => { if (alive) setData(d) })
      .catch(e => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n])
  return { data, error, loading, reload: () => setN(x => x + 1) }
}

export const Loading = () => <div className="spinner">Loading…</div>
export const ErrorBox = ({ children }) => <Alert kind="bad">{children}</Alert>

/** Message strip that clears itself. */
export function useFlash() {
  const [msg, setMsg] = useState(null)
  const show = (text, kind = 'ok') => {
    setMsg({ text, kind })
    setTimeout(() => setMsg(null), kind === 'bad' ? 8000 : 3500)
  }
  const node = msg ? <Alert kind={msg.kind}>{msg.text}</Alert> : null
  return [node, show]
}


/* ------------------------------------------------------------ printing
 * The PDF layout can be Trading (goods: HSN, quantity, delivery address)
 * or Non-trading (services: SAC, units, service period). It defaults to
 * the organisation's company type and can be switched per page.
 */
export const PRINT_VARIANTS = [
  { key: 'TRADING', label: 'Trading — goods (HSN, qty, delivery)' },
  { key: 'NONTRADING', label: 'Non-trading — services (SAC, units, period)' },
]

export function usePrintVariant() {
  const { me } = useAuth()
  const [variant, setVariant] = useState(me?.tenant?.company_type || 'NONTRADING')
  useEffect(() => { if (me?.tenant?.company_type) setVariant(me.tenant.company_type) },
    [me?.tenant?.company_type])
  return [variant, setVariant]
}

export const VariantPicker = ({ value, onChange }) => (
  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
    <span className="fine">Print layout</span>
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{ padding: '6px 9px', border: '1px solid var(--line2)', borderRadius: 7 }}>
      {PRINT_VARIANTS.map(v => <option key={v.key} value={v.key}>{v.label}</option>)}
    </select>
  </label>
)

/** "View" opens the PDF in a new tab, "PDF" downloads it. kind is the print
 *  route: invoices | purchase-orders | receipts. */
export function PrintButtons({ kind, id, variant, onError, small = true, extra = '' }) {
  const { api } = useAuth()
  const [busy, setBusy] = useState(false)
  const go = async (inline) => {
    setBusy(true)
    try { await api.printPdf(kind, id, variant, inline, extra) }
    catch (x) { onError && onError(x.message) }
    finally { setBusy(false) }
  }
  const cls = small ? 'btn btn-sm' : 'btn'
  return (<span style={{ whiteSpace: 'nowrap' }}>
    <button type="button" className={cls} disabled={busy} onClick={() => go(true)}
      title="Open the PDF in a new tab">View</button>
    <button type="button" className={cls} disabled={busy} style={{ marginLeft: 5 }}
      onClick={() => go(false)} title="Download the PDF">{busy ? '…' : 'PDF'}</button>
  </span>)
}
