import { useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Table, Tag, Alert, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { upload } from '../lib/api'

export default function Templates() {
  const { api, session } = useAuth()
  const list = useLoad(() => api.templates())
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(null)
  const [flash, showFlash] = useFlash()
  const refs = useRef({})

  if (list.loading) return <Loading />
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>

  async function send(key, file, dryRun) {
    if (!file) return
    setBusy(key); setResult(null)
    try {
      const r = await upload(
        `/templates/${key}/import${dryRun ? '?dry_run=true' : ''}`, file,
        { token: session.token, tenantId: session.tenantId })
      setResult({ key, dryRun, ...r })
      if (r.committed) showFlash(`${r.added} row(s) imported into ${r.object}.`)
      else if (r.errors.length) showFlash('Nothing was written — see the errors below.', 'bad')
    } catch (x) { setResult({ key, error: x.message }) }
    finally { setBusy(null) }
  }

  return (<>
    {flash}
    <Alert kind="ok"><b>Download the template, fill it in, upload it back.</b> Each template
      carries the exact column headings the importer expects and one worked example row you can
      overwrite or delete. <b>An import is all or nothing:</b> if any row fails, nothing at all is
      written, so a part-loaded file can never leave the books half-changed. Check first with
      <b> Check only</b> to see what would happen.</Alert>

    {list.data.map(t => {
      const r = result && result.key === t.key ? result : null
      return (
        <Panel key={t.key} title={t.label} right={
          <a className="btn btn-sm" href={api.templateUrl(t.key)}>Download template</a>}>
          <div className="fine" style={{ marginBottom: 10 }}>
            <b>Columns:</b> {t.columns.join(' · ')}</div>
          <div className="ft" style={{ marginTop: 0 }}>
            <input type="file" accept=".csv,text/csv"
              ref={el => { refs.current[t.key] = el }}
              style={{ padding: '7px 10px', border: '1px solid var(--line2)',
                borderRadius: 7, maxWidth: 300 }} />
            <button className="btn btn-sm" disabled={busy === t.key}
              onClick={() => send(t.key, refs.current[t.key]?.files?.[0], true)}>
              Check only</button>
            <button className="btn btn-sm btn-a" disabled={busy === t.key}
              onClick={() => send(t.key, refs.current[t.key]?.files?.[0], false)}>
              {busy === t.key ? 'Working…' : 'Import'}</button>
          </div>

          {r && r.error && <Alert kind="bad">{r.error}</Alert>}
          {r && !r.error && (
            <Alert kind={r.errors.length ? 'bad' : r.committed ? 'ok' : 'warn'}>
              <b>{r.rows_read} row(s) read.</b>{' '}
              {r.committed
                ? `${r.added} imported.`
                : r.errors.length
                  ? `${r.errors.length} problem(s) found — nothing was written.`
                  : `${r.would_add} would be imported.`}
              {r.skipped_existing > 0 && ` ${r.skipped_existing} skipped because they already exist.`}
              {r.errors.length > 0 && (
                <ul style={{ margin: '8px 0 0 18px', padding: 0 }}>
                  {r.errors.slice(0, 12).map((e, i) => <li key={i}>{e}</li>)}
                  {r.errors.length > 12 && <li>and {r.errors.length - 12} more</li>}
                </ul>)}
            </Alert>)}
        </Panel>)
    })}

    <Panel title="What each file expects" bodyless>
      <Table head={['Object', 'Key', { label: 'Columns', align: 'c' }, 'Notes']}>
        {list.data.map(t => (
          <tr key={t.key}>
            <td><b>{t.label}</b></td>
            <td className="mono fine">{t.key}</td>
            <td className="c mono">{t.columns.length}</td>
            <td className="fine">
              {t.key === 'customer-estimates' && 'Saved as proforma invoices, so they carry no GST liability until converted.'}
              {t.key === 'vendor-estimates' && 'Saved as purchase orders, priced at cost.'}
              {t.key === 'customer-invoices' && 'One row per line; repeat the invoice number to add lines to the same invoice.'}
              {t.key === 'vendor-invoices' && 'One row per line. Give a PO number to pull the order through.'}
              {['customers', 'vendors'].includes(t.key) && 'One contact and one bank per row. A bank or designation not on file is added.'}
              {t.key === 'materials' && 'Rates in the file are used as given, not overridden by the HSN master.'}
            </td></tr>))}
      </Table>
    </Panel>
  </>)
}
