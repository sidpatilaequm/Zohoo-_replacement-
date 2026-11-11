import { useAuth } from '../lib/auth'
import { useLoad, Loading, ErrorBox, Tag } from './ui'
import { inr } from '../lib/fmt'

/** The lines of one invoice or proforma, as the server computed them:
 *  Qty x Rate - Discount = Taxable value, then GST, then the line total.
 *  Rate and discount are shown without GST, as on the print-out, so the row
 *  adds up on lines that were quoted inclusive of GST too. */
export default function InvoiceLines({ id }) {
  const { api } = useAuth()
  const d = useLoad(() => api.invoice(id), [id])
  if (d.loading) return <Loading />
  if (d.error) return <ErrorBox>{d.error}</ErrorBox>

  const t = d.data.totals
  const hasDisc = t.discount > 0.004
  const th = (label, r) => <th className={r ? 'r' : ''}>{label}</th>

  return (<div className="lines-box">
    <table className="lines">
      <thead><tr>
        {th('#')}{th('Item')}{th('HSN/SAC')}{th('Qty', 1)}{th('Rate', 1)}
        {hasDisc && th('Discount', 1)}{th('Taxable value', 1)}
        {th('GST', 1)}{th('Tax', 1)}{th('Line total', 1)}
      </tr></thead>
      <tbody>{t.lines.map(L => (<tr key={L.line_no}>
        <td className="mono">{L.line_no}</td>
        <td>{L.descr}<div className="fine mono">{L.code}</div></td>
        <td className="mono">{L.hsn}</td>
        <td className="r mono">{L.qty} <span className="fine">{L.uom}</span></td>
        <td className="r mono">{inr(L.unit_rate)}
          {L.inclusive && <div className="fine">{inr(L.price)} incl. GST</div>}</td>
        {hasDisc && <td className="r mono">{L.discount > 0.004 ? inr(L.discount) : '—'}
          {L.discount > 0.004 && <div className="fine">
            {[L.disc_type === 'PCT' ? `${L.disc_value}%` : L.disc_type === 'AMT' ? 'line' : null,
              L.overall_disc > 0.004 ? 'overall' : null].filter(Boolean).join(' + ')}</div>}</td>}
        <td className="r mono"><b>{inr(L.amount)}</b></td>
        <td className="r mono">{L.rate}%{t.intra
          ? <div className="fine">CGST {L.rate / 2}% · SGST {L.rate / 2}%</div>
          : <div className="fine">IGST</div>}</td>
        <td className="r mono">{inr(L.cgst + L.sgst + L.igst)}</td>
        <td className="r mono">{inr(L.total)}</td>
      </tr>))}</tbody>
    </table>
    <div className="lines-sum">
      {hasDisc && <>
        <span>Items total <b className="mono">{inr(t.gross)}</b></span>
        <span>Discount <b className="mono">− {inr(t.discount)}</b>
          {t.overall_discount > 0 && <span className="fine"> (incl. overall
            {t.disc_type === 'PCT' ? ` ${t.disc_value}%` : ''} {inr(t.overall_discount)})</span>}</span>
      </>}
      <span>Taxable <b className="mono">{inr(t.taxable)}</b></span>
      {t.intra
        ? <><span>CGST <b className="mono">{inr(t.cgst)}</b></span>
            <span>SGST <b className="mono">{inr(t.sgst)}</b></span></>
        : <span>IGST <b className="mono">{inr(t.igst)}</b></span>}
      {Math.abs(t.roundoff) >= 0.005 && <span>Round off <b className="mono">{inr(t.roundoff)}</b></span>}
      <span>Total <b className="mono">₹ {inr(t.rounded)}</b></span>
      {t.lines.some(L => L.inclusive) && <Tag kind="warn">some lines quoted incl. GST</Tag>}
    </div>
  </div>)
}
