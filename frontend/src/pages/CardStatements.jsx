import { useState } from 'react'
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

  const cards = (accounts.data || []).filter(a => a.kind === 'CARD')
  const aid = Number(acct) || cards[0]?.id
  const card = cards.find(c => c.id === aid)
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
      const r = await api.uploadStmt(aid, period, file)
      showFlash(r.saved
        ? `${r.saved} transaction(s) saved${r.duplicates_skipped ? `, ${r.duplicates_skipped} already on record` : ''}. Debits start as Unallocated — decide company or personal below.`
        : r.note || 'Nothing new in this file.')
      setFile(null); txns.reload(); recon.reload()
    } catch (x) { showFlash(x.message, 'bad') }
    finally { setBusy(false) }
  }

  async function setAlloc(t, allocation, category) {
    try {
      await api.allocateTxn(t.id, { allocation,
        category: allocation === 'COMPANY' ? (category || 'Other') : null, notes: t.notes || null })
      txns.reload(); recon.reload()
    } catch (x) { showFlash(x.message, 'bad') }
  }

  if (accounts.loading) return <Loading />
  if (accounts.error) return <ErrorBox>{accounts.error}</ErrorBox>

  const rows = (txns.data || []).filter(t =>
    only === 'ALL' || (t.allocation === 'UNALLOCATED' && t.debit > 0))
  const mine = (recon.data || []).find(r => r.account.id === aid)

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
        <form onSubmit={addCard} style={{ display: 'flex', gap: 6 }}>
          <input placeholder="New card label" value={na.label} style={{ width: 130 }}
            onChange={e => setNa(s => ({ ...s, label: e.target.value }))} />
          <input placeholder="Director" value={na.holder} style={{ width: 110 }}
            onChange={e => setNa(s => ({ ...s, holder: e.target.value }))} />
          <button className="btn btn-sm" disabled={!na.label || !na.holder}>Add card</button>
        </form>}>
        <form onSubmit={doUpload}><div className="row">
          <Field label="Card">
            <select value={aid} onChange={e => setAcct(e.target.value)}>
              {cards.map(a => <option key={a.id} value={a.id}>
                {a.label} — {a.holder}{a.number_hint ? ` ··${a.number_hint}` : ''}</option>)}
            </select></Field>
          <Field label="Statement month">
            <input type="month" value={period} onChange={e => setPeriod(e.target.value)} required /></Field>
          <Field label="Statement file" hint="PDF or CSV">
            <input type="file" accept=".pdf,.csv,.txt"
              onChange={e => setFile(e.target.files[0] || null)} /></Field>
          <Field label=" "><button className="btn btn-a" disabled={busy || !file}>
            {busy ? 'Reading…' : 'Upload and save'}</button></Field>
        </div></form>
      </Panel>

      <Panel title={`Allocate — ${card?.label || ''} · ${period}`} right={
        <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="fine">Show</span>
          <select value={only} onChange={e => setOnly(e.target.value)}>
            <option value="ALL">Everything</option>
            <option value="UNALLOCATED">Only unallocated spends</option>
          </select></label>}>
        {txns.loading ? <Loading /> : txns.error ? <ErrorBox>{txns.error}</ErrorBox> :
          <Table head={['Date', 'Description', { label: 'Amount', align: 'r' }, 'Status',
            'Allocate to', 'Expense category']}
            empty="No transactions saved for this card and month yet.">
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
                  <select value={t.category || 'Other'}
                    onChange={e => setAlloc(t, 'COMPANY', e.target.value)}>
                    {(cats.data || ['Other']).map(c => <option key={c}>{c}</option>)}
                  </select>}</td>
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
