import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Alert, Loading } from './ui'

/** Mail a proforma, tax invoice (kind="invoice") or purchase order (kind="po").
 *  The draft (from, to, subject, body, attachment name) comes from the server;
 *  the user edits it here and the server sends it through the organisation's SMTP. */
const split = s => s.split(/[,;\s]+/).map(x => x.trim()).filter(Boolean)
const MAX_EXTRA = 10 * 1024 * 1024

function readB64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader()
    r.onload = () => res(String(r.result).split('base64,')[1] || '')
    r.onerror = () => rej(new Error(`Could not read ${file.name}`))
    r.readAsDataURL(file)
  })
}

export default function EmailComposer({ kind, id, variant, onClose, onSent }) {
  const { api, can } = useAuth()
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [f, setF] = useState(null)
  const [extra, setExtra] = useState([])
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const fileRef = useRef()
  const firstRef = useRef()

  useEffect(() => {
    let alive = true
    api.emailDraft(kind, id, variant).then(x => {
      if (!alive) return
      setD(x)
      setF({ to: x.to.join(', '), cc: x.cc.join(', '), bcc: x.bcc.join(', '),
        subject: x.subject, body: x.body, attach: true })
    }).catch(e => alive && setErr(e.message))
    return () => { alive = false }
  }, [api, kind, id, variant])

  useEffect(() => {
    const esc = e => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [busy, onClose])
  useEffect(() => { if (f && firstRef.current) firstRef.current.focus() }, [!!f]) // eslint-disable-line

  const set = (k, v) => setF(s => ({ ...s, [k]: v }))
  const addTo = a => { const cur = split(f.to); if (!cur.includes(a)) set('to', [...cur, a].join(', ')) }

  async function pick(e) {
    const files = [...(e.target.files || [])]; e.target.value = ''
    const size = [...extra, ...files].reduce((n, x) => n + (x.size || 0), 0)
    if (size > MAX_EXTRA) { setErr('Extra files come to more than 10 MB.'); return }
    setExtra(x => [...x, ...files].slice(0, 10))
  }

  async function send(e) {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const files = await Promise.all(extra.map(async x => ({ filename: x.name,
        content_type: x.type || 'application/octet-stream', content_base64: await readB64(x) })))
      const r = await api.emailSend({ kind, id, variant, to: split(f.to), cc: split(f.cc),
        bcc: split(f.bcc), subject: f.subject, body: f.body, attach_pdf: f.attach, extra: files })
      setDone(r); onSent && onSent(r)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  const preview = () => api.printPdf(kind === 'po' ? 'purchase-orders' : 'invoices', id, variant, true)
    .catch(x => setErr(x.message))

  return (
    <div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget && !busy) onClose() }}>
      <div className="modal mail" role="dialog" aria-modal="true" aria-labelledby="mail-title">
        <div className="modal-hd">
          <h2 id="mail-title">{d ? `Email ${d.doc_label} ${d.doc_no}` : 'Email document'}</h2>
          <button type="button" className="rm" aria-label="Close" onClick={onClose} disabled={busy}>×</button>
        </div>
        {!d && !err && <div className="modal-bd"><Loading /></div>}
        {!d && err && <div className="modal-bd"><Alert kind="bad">{err}</Alert></div>}
        {d && done && <div className="modal-bd">
          <Alert kind="ok"><b>Sent.</b> {d.doc_label} {d.doc_no} went to {done.to.join(', ')}
            {done.cc.length ? `, copy to ${done.cc.join(', ')}` : ''}, with{' '}
            {done.attachments.length ? done.attachments.join(', ') : 'no attachment'}.</Alert>
          {Object.keys(done.refused || {}).length > 0 && <Alert kind="warn">
            The server refused: {Object.keys(done.refused).join(', ')}.</Alert>}
          <div className="ft"><button className="btn btn-a" onClick={onClose}>Close</button></div>
        </div>}
        {d && f && !done && <form className="modal-bd" onSubmit={send}>
          {!d.smtp_ready && <Alert kind="warn">
            <b>Mail is not set up yet:</b> {d.smtp_problems.join('; ')}.{' '}
            {can('org') ? <Link to="/company" onClick={onClose}>Open Company Information → Email and SMTP</Link>
              : 'Ask an administrator to fill in Company Information → Email and SMTP.'}</Alert>}
          <div className="mail-h">
            <label>From</label>
            <div className="mail-from">{d.from || <span className="fine">not set</span>}
              {d.reply_to && <span className="fine"> (replies to {d.reply_to})</span>}</div>
            <label htmlFor="m-to">To</label>
            <div><input id="m-to" ref={firstRef} value={f.to} required
              placeholder="name@company.com, another@company.com" onChange={e => set('to', e.target.value)} />
              {d.suggestions.filter(a => !split(f.to).includes(a)).length > 0 &&
                <div className="mail-sugg">On file for {d.party}:{' '}
                  {d.suggestions.filter(a => !split(f.to).includes(a)).map(a =>
                    <button type="button" key={a} className="chip" onClick={() => addTo(a)}>+ {a}</button>)}</div>}</div>
            <label htmlFor="m-cc">Cc</label>
            <input id="m-cc" value={f.cc} onChange={e => set('cc', e.target.value)} />
            <label htmlFor="m-bcc">Bcc</label>
            <input id="m-bcc" value={f.bcc} onChange={e => set('bcc', e.target.value)} />
            <label htmlFor="m-subj">Subject</label>
            <input id="m-subj" value={f.subject} required maxLength={250}
              onChange={e => set('subject', e.target.value)} />
          </div>
          <textarea className="mail-body" aria-label="Message" value={f.body} rows={11}
            onChange={e => set('body', e.target.value)} />
          <div className="mail-att">
            <label className="att">
              <input type="checkbox" checked={f.attach} onChange={e => set('attach', e.target.checked)} />
              <span className="att-ic">PDF</span>
              <span><b>{d.attachment}</b><span className="fine"> generated now, as View shows it</span></span>
            </label>
            <button type="button" className="btn btn-sm" onClick={preview}>Preview</button>
            {extra.map((x, i) => <span key={i} className="att">
              <span className="att-ic">{(x.name.split('.').pop() || 'file').slice(0, 4)}</span>{x.name}
              <button type="button" className="rm" aria-label={`Remove ${x.name}`}
                onClick={() => setExtra(extra.filter((_, j) => j !== i))}>×</button></span>)}
            <button type="button" className="btn btn-sm" onClick={() => fileRef.current.click()}>Add files</button>
            <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={pick} />
          </div>
          {d.history.length > 0 && <div className="mail-hist">
            <div className="fine">Sent before</div>
            {d.history.map(h => <div key={h.id} className={h.status === 'FAILED' ? 'bad' : ''}>
              {new Date(h.sent_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
              {' — '}{h.status === 'FAILED' ? 'failed' : 'sent'} to {h.to}{h.sent_by ? ` by ${h.sent_by}` : ''}
              {h.status === 'FAILED' && h.error ? `: ${h.error}` : ''}</div>)}
          </div>}
          <div className="ft">
            <button className="btn btn-a" disabled={busy || !d.smtp_ready}>{busy ? 'Sending…' : 'Send'}</button>
            <button type="button" className="btn" onClick={onClose} disabled={busy}>Cancel</button>
            {err && <span className="err">{err}</span>}
          </div>
        </form>}
      </div>
    </div>)
}
