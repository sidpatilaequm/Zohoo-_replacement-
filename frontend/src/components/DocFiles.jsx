import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Alert, Tag } from './ui'

const MAX_BYTES = 10 * 1024 * 1024

function size(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function DocFiles({ kind, id }) {
  const { api } = useAuth()

  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function load() {
    setLoading(true)
    setErr(null)

    try {
      const rows = kind === 'vinv'
        ? await api.vinvDocuments(id)
        : await api.invoiceDocuments(id)

      setFiles(rows || [])
    } catch (x) {
      setErr(x.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) load()
  }, [id, kind])

  async function add(e) {
    const file = e.target.files?.[0]
    e.target.value = ''

    if (!file) return

    if (file.size > MAX_BYTES) {
      setErr('The maximum document size is 10 MB.')
      return
    }

    setBusy(true)
    setErr(null)

    try {
      if (kind === 'vinv') {
        await api.addVinvDocument(id, file)
      } else {
        await api.addInvoiceDocument(id, file)
      }

      await load()
    } catch (x) {
      setErr(x.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(file) {
    if (!window.confirm(`Delete "${file.filename}"?`)) return

    try {
      await api.delDocument(file.id)
      await load()
    } catch (x) {
      setErr(x.message)
    }
  }

  async function open(file) {
    try {
      await api.openDocument(file.id, !!file.viewable)
    } catch (x) {
      setErr(x.message)
    }
  }

  return (
    <Panel title={`Supporting documents — ${files.length}`}>
      {err && <Alert kind="bad">{err}</Alert>}

      <div className="ft" style={{ marginTop: 0 }}>
        <input
          type="file"
          disabled={busy}
          onChange={add}
          accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.heic,.doc,.docx,.xls,.xlsx,.csv,.txt,.eml,.msg,.zip"
          style={{
            padding: '7px 10px',
            border: '1px solid var(--line2)',
            borderRadius: 7,
            maxWidth: 360
          }}
        />

        <span className="fine">
          {busy
            ? 'Uploading…'
            : 'PDF, images, Office files, e-mail or ZIP · maximum 10 MB'}
        </span>
      </div>

      {loading ? (
        <div className="fine" style={{ marginTop: 10 }}>
          Loading documents…
        </div>
      ) : files.length === 0 ? (
        <div className="fine" style={{ marginTop: 10 }}>
          No supporting documents attached.
        </div>
      ) : (
        <div style={{ marginTop: 10 }}>
          {files.map(file => (
            <div
              key={file.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '9px 0',
                borderTop: '1px solid var(--line)'
              }}
            >
              <div style={{ flex: 1 }}>
                <b>{file.filename}</b>
                <span className="fine" style={{ marginLeft: 8 }}>
                  {size(file.size)}
                </span>

                {file.notes && (
                  <div className="fine">{file.notes}</div>
                )}

                <div className="fine">
                  {file.uploaded_by || '—'}
                  {file.at
                    ? ` · ${new Date(file.at).toLocaleString()}`
                    : ''}
                </div>
              </div>

              {file.viewable && <Tag kind="ok">Viewable</Tag>}

              <button
                type="button"
                className="btn btn-sm"
                onClick={() => open(file)}
              >
                {file.viewable ? 'Open' : 'Download'}
              </button>

              <button
                type="button"
                className="btn btn-sm"
                style={{ color: 'var(--red)' }}
                onClick={() => remove(file)}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}