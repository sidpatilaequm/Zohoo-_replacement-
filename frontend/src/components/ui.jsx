import { useEffect, useState } from 'react'

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
