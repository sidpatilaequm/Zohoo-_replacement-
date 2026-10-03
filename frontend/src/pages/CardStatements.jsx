import { useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Panel, Field, Table, Alert, Tag, useLoad, Loading, ErrorBox, useFlash } from '../components/ui'
import { inr, money, gd } from '../lib/fmt'

const thisMonth = () => new Date().toISOString().slice(0, 7)
const ALLOC_TAG = { COMPANY: 'ok', PERSONAL: 'no', UNALLOCATED: 'warn' }

export default function CardStatements() {
  const { api } = useAuth()
  const accounts = useLoad(() => api.stmtAccounts())
  const cats = useLoad(() => api.stmtCategories())
  const [acct, setAcct] = useState('')
  const [period, setPeriod] = useState(thisMonth())
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [flash, showFlash] = useFlash()
  const [na, setNa] = useState({ label: '', holder: '', number_hint: '' })
  const [only, setOnly] = useState('ALL')   // ALL | UNALLOCATED
  // How the spends in the file being uploaded are marked as they are saved.
  const [mark, setMark] = useState('UNALLOCATED')   // UNALLOCATED | COMPANY | PERSONAL
  const [markCat, setMarkCat] = useState('Other')
  const [bulkCat, setBulkCat] = useState('Other')
  const [uploads, setUploads] = useState([])
  const [uploadsLoading, setUploadsLoading] = useState(false)
  const [docFiles, setDocFiles] = useState({})
  const [docBusy, setDocBusy] = useState({})
  // Heads come from the Expense master; default to its first one.
  const firstCat = cats.data?.[0] || 'Other'
  useEffect(() => {
    if (!cats.data?.length) return
    if (!cats.data.includes(markCat)) setMarkCat(cats.data[0])
    if (!cats.data.includes(bulkCat)) setBulkCat(cats.data[0])
  }, [cats.data]) // eslint-disable-line

  const cards = (accounts.data || []).filter(a => a.kind === 'CARD')
  const aid = Number(acct) || cards[0]?.id
  const card = cards.find(c => c.id === aid)

  async function loadUploads() {
  if (!aid) {
    setUploads([])
    return
  }

  setUploadsLoading(true)
  try {
    setUploads(await api.stmtUploads(aid))
  } catch (x) {
    showFlash(x.message, 'bad')
  } finally {
    setUploadsLoading(false)
  }
}

useEffect(() => {
  loadUploads()
}, [aid])

  const txns = useLoad(() => aid ? api.stmtTxns(aid, period) : [], [aid, period])
  const recon = useLoad(() => api.stmtReconcile(period), [period])

  async function addCard(e) {
    e.preventDefault()
    try {
      await api.addStmtAccount({ kind: 'CARD', label: na.label, holder: na.holder,
        number_hint: na.number_hint || null })
      setNa({ label: '', holder: '', number_hint: '' }); accounts.reload()
      showFlash('Card added.')
    } catch (x) { showFlash(x.message, 'bad') }
  }

  async function doUpload(e) {
    e.preventDefault()
    if (!file) return showFlash('Choose the card statement first.', 'bad')
    setBusy(true)
    try {
      const r = await api.uploadStmt(aid, period, file, { allocation: mark, category: markCat })
      const how = mark === 'COMPANY' ? `Spends are marked company expense (${markCat}) — change any single one below.`
        : mark === 'PERSONAL' ? 'Spends are marked personal — change any single one below.'
        : 'Spends start as unallocated — decide company or personal below.'
      const cycle = r.statement_period
        ? ` Statement period ${gd(r.statement_period[0])} to ${gd(r.statement_period[1])}.` : ''
      const skipped = r.outside_period_ignored
        ? ` ${r.outside_period_ignored} line(s) dated outside it (illustrations, not transactions) were ignored.` : ''
      showFlash(r.saved
        ? `${r.saved} transaction(s) saved${r.duplicates_skipped ? `, ${r.duplicates_skipped} already on record` : ''}.${cycle}${skipped} ${how}`
        : (r.note || 'Nothing new in this file.') + cycle)
      setFile(null)
      loadUploads()
      txns.reload()
      recon.reload()
    } catch (x) { showFlash(x.message, 'bad') }
    finally { setBusy(false) }
  }
    async function loadTxnDocuments(txnId) {
    try {
      const docs = await api.stmtDocuments(txnId)
      setDocFiles(s => ({ ...s, [txnId]: docs }))
    } catch (x) {
      showFlash(x.message, 'bad')
    }
  }

  async function uploadTxnDocument(txnId, file) {
    if (!file) return

    setDocBusy(s => ({ ...s, [txnId]: true }))

    try {
      await api.addStmtDocument(txnId, file)
      await loadTxnDocuments(txnId)
      showFlash('Supporting document uploaded.')
    } catch (x) {
      showFlash(x.message, 'bad')
    } finally {
      setDocBusy(s => ({ ...s, [txnId]: false }))
    }
  }

async function uploadTxnDocument(txnId, file) {
  if (!file) return

  setDocBusy(s => ({ ...s, [txnId]: true }))

  try {
    await api.addStmtDocument(txnId, file)
    await loadTxnDocuments(txnId)
    showFlash('Supporting document uploaded.')
  } catch (x) {
    showFlash(x.message, 'bad')
  } finally {
    setDocBusy(s => ({ ...s, [txnId]: false }))
  }
}
  async function removeCard() {
    if (!aid) return

    let imp
    try {
      imp = await api.stmtAccountImpact(aid)
    } catch (x) {
      return showFlash(x.message, 'bad')
    }

    const account = cards.find(a => a.id === aid)
    if (!account) return

    const lines = [
      `Delete the card "${account.label}" completely?`,
      '',
      `• ${imp.statements} uploaded statement(s) and ${imp.transactions} transaction(s) will be deleted.`
    ]

    if (imp.allocated) {
      lines.push(`• ${imp.allocated} transaction(s) marked company or personal — those decisions go too.`)
    }
    if (imp.attachments) {
      lines.push(`• ${imp.attachments} attachment(s) to invoices, employees or loans will be removed.`)
    }
    if (imp.recorded_payments) {
      lines.push(`• ${imp.recorded_payments} receipt(s) or payment(s) recorded from those attachments will be removed, so those invoices show as unpaid again.`)
    }

    lines.push(
      '',
      'Invoices, vendors, employees and loans themselves are not touched.',
      'This cannot be undone.'
    )

    let confirm = null

    if (imp.allocated || imp.attachments) {
      confirm = window.prompt(
        lines.join('\n') +
        `\n\nType the card name to confirm: ${account.label}`
      )

      if (confirm === null) return

      if (confirm.trim() !== account.label) {
        return showFlash(`The name did not match "${account.label}" — nothing was deleted.`, 'bad')
      }
    } else {
      if (!window.confirm(lines.join('\n'))) return
    }

    setBusy(true)

    try {
      const r = await api.delStmtAccount(aid, confirm)

      showFlash(
        `Deleted ${r.label} — ${r.statements} statement(s), ${r.transactions} transaction(s)` +
        (r.attachments ? `, ${r.attachments} attachment(s)` : '') +
        (r.payments_removed ? `, ${r.payments_removed} recorded receipt(s)/payment(s)` : '') +
        '.'
      )

      setAcct('')
      setUploads([])
      accounts.reload()
      txns.reload()
      recon.reload()
    } catch (x) {
      showFlash(x.message, 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function setAlloc(t, allocation, category) {
    try {
      await api.allocateTxn(t.id, { allocation,
        category: allocation === 'COMPANY' ? (category || firstCat) : null, notes: t.notes || null })
      txns.reload(); recon.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }

  async function markAll(allocation) {
    const what = allocation === 'COMPANY' ? `company expense (${bulkCat})` : 'personal'
    if (!window.confirm(`Mark every unallocated spend on this card for ${period} as ${what}?`)) return
    try {
      const r = await api.allocateAll(aid, period, { allocation,
        category: allocation === 'COMPANY' ? bulkCat : null })
      showFlash(r.updated ? `${r.updated} spend(s) marked ${what}.` : 'No unallocated spends left.')
      txns.reload(); recon.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }

  if (accounts.loading) return <Loading />
  if (accounts.error) return <ErrorBox>{accounts.error}</ErrorBox>

  const rows = (txns.data || []).filter(t =>
    only === 'ALL' || (t.allocation === 'UNALLOCATED' && t.debit > 0))
  const mine = (recon.data || []).find(r => r.account.id === aid)
  const unallocCount = (txns.data || []).filter(t => t.allocation === 'UNALLOCATED' && t.debit > 0).length

  return (<>
    {flash}
    <Alert kind="ok"><b>Cards a director pays personally.</b> Upload each month's card
      statement — every transaction is saved once — then mark each spend as a
      <b> company expense</b> (the company owes the director for it) or as
      <b> personal</b>. The reconciliation below totals what the company owes the director,
      and company expenses flow into the monthly expense ledger on the Bank Statements screen.</Alert>

    {!cards.length && <Panel title="Add a director's card first">
      <form onSubmit={addCard}><div className="row">
        <Field label="Card label" hint="e.g. RBL Platinum Plus">
          <input value={na.label} onChange={e => setNa(s => ({ ...s, label: e.target.value }))} required /></Field>
        <Field label="Director (card holder)">
          <input value={na.holder} onChange={e => setNa(s => ({ ...s, holder: e.target.value }))} required /></Field>
        <Field label="Last digits"><input value={na.number_hint}
          onChange={e => setNa(s => ({ ...s, number_hint: e.target.value }))} /></Field>
        <Field label=" "><button className="btn btn-a">Add card</button></Field>
      </div></form>
    </Panel>}

    {cards.length > 0 && <>
      <Panel title="Upload a card statement" right={
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <form onSubmit={addCard} style={{ display: 'flex', gap: 6 }}>
            <input placeholder="New card label" value={na.label} style={{ width: 130 }}
              onChange={e => setNa(s => ({ ...s, label: e.target.value }))} />
            <input placeholder="Director" value={na.holder} style={{ width: 110 }}
              onChange={e => setNa(s => ({ ...s, holder: e.target.value }))} />
            <button className="btn btn-sm" disabled={!na.label || !na.holder}>Add card</button>
          </form>
          {aid && <button
            type="button"
            className="btn btn-sm"
            style={{ color: 'var(--red)' }}
            disabled={busy}
            onClick={removeCard}
          >
            {busy ? 'Deleting…' : 'Delete card'}
          </button>}
        </div>}>
        <form onSubmit={doUpload}><div className="row">
          <Field label="Card">
            <select value={aid} onChange={e => setAcct(e.target.value)}>
              {cards.map(a => <option key={a.id} value={a.id}>
                {a.label} — {a.holder}{a.number_hint ? ` ··${a.number_hint}` : ''}</option>)}
            </select></Field>
          <Field label="Statement month" hint="The month the bill is dated; its rows are listed under it">
            <input type="month" value={period} onChange={e => setPeriod(e.target.value)} required /></Field>
          <Field label="Statement file" hint="PDF or CSV">
            <input type="file" accept=".pdf,.csv,.txt"
              onChange={e => setFile(e.target.files[0] || null)} /></Field>
        </div>
        <div className="row" style={{ marginTop: 13 }}>
          <Field label="Spends in this statement are"
            hint="Applied as the file is saved. Any single spend can still be changed below.">
            <select value={mark} onChange={e => setMark(e.target.value)}>
              <option value="UNALLOCATED">Undecided — I will mark each one</option>
              <option value="COMPANY">Company expense</option>
              <option value="PERSONAL">Personal expense</option>
            </select></Field>
          {mark === 'COMPANY' && <Field label="Expense head" hint="From the Expenses master">
            <select value={markCat} onChange={e => setMarkCat(e.target.value)}>
              {(cats.data || ['Other']).map(c => <option key={c}>{c}</option>)}
            </select></Field>}
          <Field label=" "><button className="btn btn-a" disabled={busy || !file}>
            {busy ? 'Reading…' : 'Upload and save'}</button></Field>
        </div></form>
      </Panel>

      <Panel title={`Allocate — ${card?.label || ''} · ${period}`} right={<>
        {unallocCount > 0 && <span style={{ fontSize: 12, display: 'flex', gap: 5, alignItems: 'center' }}>
          <span className="fine">Mark {unallocCount} undecided as</span>
          <select value={bulkCat} onChange={e => setBulkCat(e.target.value)} style={{ width: 150 }}
            title="Expense head used for company">
            {(cats.data || ['Other']).map(c => <option key={c}>{c}</option>)}
          </select>
          <button type="button" className="btn btn-sm" onClick={() => markAll('COMPANY')}>
            Company</button>
          <button type="button" className="btn btn-sm" onClick={() => markAll('PERSONAL')}>
            Personal</button></span>}
        <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="fine">Show</span>
          <select value={only} onChange={e => setOnly(e.target.value)}>
            <option value="ALL">Everything</option>
            <option value="UNALLOCATED">Only unallocated spends</option>
          </select></label></>}>
        {txns.loading ? <Loading /> : txns.error ? <ErrorBox>{txns.error}</ErrorBox> :
          <Table
            head={['Date', 'Description', { label: 'Amount', align: 'r' }, 'Status',
              'Allocate to', 'Expense head', 'Supporting document']}
            empty="No transactions saved for this card and month yet."
          >
            {rows.map(t => {
              const isPayment = t.debit === 0
              return <tr key={t.id}>
                <td>{gd(t.date)}</td><td>{t.descr}</td>
                <td className="r mono">{isPayment ? `− ${inr(t.credit)}` : inr(t.debit)}</td>
                <td>{isPayment ? <Tag kind="ok">payment / refund</Tag>
                  : <Tag kind={ALLOC_TAG[t.allocation]}>{t.allocation.toLowerCase()}</Tag>}</td>
                <td>{!isPayment && <span style={{ whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn btn-sm"
                    disabled={t.allocation === 'COMPANY'}
                    onClick={() => setAlloc(t, 'COMPANY', t.category)}>Company</button>
                  <button type="button" className="btn btn-sm" style={{ marginLeft: 5 }}
                    disabled={t.allocation === 'PERSONAL'}
                    onClick={() => setAlloc(t, 'PERSONAL')}>Personal</button></span>}</td>
                <td>{!isPayment && t.allocation === 'COMPANY' &&
                  <select value={t.category || firstCat}
                    onChange={e => setAlloc(t, 'COMPANY', e.target.value)}>
                    {(cats.data || ['Other']).map(c => <option key={c}>{c}</option>)}
                  </select>}</td>
                  <td>

                    {!isPayment && (
                      <div style={{ minWidth: 190 }}>
                        {(docFiles[t.id] || []).map(d => (
                          <div key={d.id} style={{ marginBottom: 5 }}>
                            <a
                              href={api.openDocument(d.id)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {d.filename}
                            </a>
                          </div>
                        ))}

                        <input
                          type="file"
                          accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.heic,.doc,.docx,.xls,.xlsx,.csv,.txt,.eml,.msg,.zip"
                          disabled={docBusy[t.id]}
                          onChange={e => {
                            const f = e.target.files[0]
                            e.target.value = ''
                            uploadTxnDocument(t.id, f)
                          }}
                        />

                        {!docFiles[t.id] && (
                          <button
                            type="button"
                            className="btn btn-sm"
                            style={{ marginTop: 5 }}
                            onClick={() => loadTxnDocuments(t.id)}
                          >
                            Load documents
                          </button>
                        )}
                      </div>
                    )}
                  </td>
              </tr>})}
          </Table>}
      </Panel>

      {mine && <Panel title={`Reconciliation with the director — ${period}`}>
        <Table head={['', { label: 'Amount', align: 'r' }]}>
          <tr><td>Spent for the company (owed to {card?.holder || 'the director'})</td>
            <td className="r mono">{inr(mine.company)}</td></tr>
          <tr><td>Personal spend (director's own)</td>
            <td className="r mono">{inr(mine.personal)}</td></tr>
          <tr><td>Still unallocated</td>
            <td className="r mono">{mine.unallocated ? inr(mine.unallocated) : '—'}</td></tr>
          <tr><td>Payments made onto the card this month</td>
            <td className="r mono">{inr(mine.payments)}</td></tr>
          <tr style={{ fontWeight: 600 }}>
            <td>Company owes {card?.holder || 'the director'} for this month</td>
            <td className="r mono">{inr(mine.owed_to_director)}</td></tr>
        </Table>
        {mine.unallocated > 0 &&
          <Alert kind="warn">{money(mine.unallocated)} of spends are still unallocated —
            the amount owed is complete only once every spend is decided.</Alert>}
        {mine.by_category.length > 0 && <>
          <div className="fine" style={{ margin: '12px 0 6px' }}>Company expense by category
            (these amounts appear in the monthly expense ledger)</div>
          <Table head={['Category', { label: 'Amount', align: 'r' }]}>
            {mine.by_category.map(c => <tr key={c.category}>
              <td>{c.category}</td><td className="r mono">{inr(c.amount)}</td></tr>)}
          </Table></>}
      </Panel>}

      {(recon.data || []).length > 1 && <Panel title={`All director cards — ${period}`}>
        <Table head={['Card', 'Director', { label: 'Company', align: 'r' },
          { label: 'Personal', align: 'r' }, { label: 'Unallocated', align: 'r' },
          { label: 'Payments', align: 'r' }]}>
          {recon.data.map(r => <tr key={r.account.id}>
            <td>{r.account.label}</td><td>{r.account.holder}</td>
            <td className="r mono">{inr(r.company)}</td>
            <td className="r mono">{inr(r.personal)}</td>
            <td className="r mono">{r.unallocated ? inr(r.unallocated) : '—'}</td>
            <td className="r mono">{inr(r.payments)}</td></tr>)}
        </Table>
      </Panel>}
    </>}
  </>)
}
