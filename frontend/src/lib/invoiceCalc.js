/** The invoice arithmetic, as backend/app/tax.py does it, for the running
 *  totals on the New Invoice screen. The server recomputes on save and its
 *  figures are the ones stored and printed; this mirrors it rule for rule so
 *  the screen and the print-out agree.
 *
 *  Discounts come off before GST. A line discount (PCT or AMT) comes off its
 *  line; the overall discount is then spread over the lines in proportion to
 *  what each is worth after its own discount, with any paise left over going
 *  to the largest line. On a GST-inclusive line the discount is off the
 *  quoted (inclusive) figure and the tax is carved out of what remains. */

export const r2 = n => Math.round((Number(n) + Number.EPSILON) * 100) / 100

export function discAmount(base, type, value) {
  const v = Number(value || 0)
  if (!type || !(v > 0) || !(base > 0)) return 0
  const amt = type === 'PCT' ? r2(base * v / 100) : r2(v)
  return Math.min(amt, r2(base))
}

export function spread(total, weights) {
  const base = weights.reduce((a, w) => a + w, 0)
  if (!(total > 0) || !(base > 0)) return weights.map(() => 0)
  const shares = weights.map(w => r2(total * w / base))
  const diff = r2(total - shares.reduce((a, s) => a + s, 0))
  if (diff) {
    let big = 0
    weights.forEach((w, k) => { if (w > weights[big]) big = k })
    shares[big] = r2(shares[big] + diff)
  }
  return shares
}

/** lines: [{ qty, price, incl, cgst, sgst, igst, disc_type, disc_value }]
 *  (cgst/sgst/igst are the percentages that apply to the line). */
export function computeInvoice(lines, intra, overall = {}) {
  const prep = lines.map(l => {
    const listValue = r2(Number(l.qty || 0) * Number(l.price || 0))
    const lineDisc = discAmount(listValue, l.disc_type, l.disc_value)
    return { ...l, listValue, lineDisc }
  })
  const after = prep.map(p => r2(p.listValue - p.lineDisc))
  const afterTotal = r2(after.reduce((a, x) => a + x, 0))
  const overallDisc = discAmount(afterTotal, overall.disc_type, overall.disc_value)
  const shares = spread(overallDisc, after)

  let taxable = 0, cgst = 0, sgst = 0, igst = 0, gross = 0, lineDiscount = 0
  const rows = prep.map((p, k) => {
    const share = shares[k]
    const net = r2(p.listValue - p.lineDisc - share)
    const pc = Number(p.cgst || 0), ps = Number(p.sgst || 0), pi = Number(p.igst || 0)
    const rate = intra ? pc + ps : pi
    let amount, value, c, s, i, total
    if (p.incl) {
      amount = rate ? r2(net * 100 / (100 + rate)) : net
      value = rate ? r2(p.listValue * 100 / (100 + rate)) : p.listValue
      const carved = r2(net - amount)
      if (intra) {
        c = (pc + ps) ? r2(carved * pc / (pc + ps)) : 0
        s = r2(carved - c); i = 0
      } else { c = 0; s = 0; i = carved }
      total = net
    } else {
      amount = net; value = p.listValue
      c = intra ? r2(amount * pc / 100) : 0
      s = intra ? r2(amount * ps / 100) : 0
      i = intra ? 0 : r2(amount * pi / 100)
      total = r2(amount + c + s + i)
    }
    taxable += amount; cgst += c; sgst += s; igst += i
    gross += value; lineDiscount += p.lineDisc
    return { ...p, share, net, amount, value, discount: r2(value - amount),
      c, s, i, rate, total }
  })
  taxable = r2(taxable); cgst = r2(cgst); sgst = r2(sgst); igst = r2(igst)
  gross = r2(gross)
  const sum = r2(taxable + cgst + sgst + igst)
  const rounded = Math.round(sum)
  return { rows, taxable, cgst, sgst, igst, gross, discount: r2(gross - taxable),
    lineDiscount: r2(lineDiscount), overallDisc, afterLineDisc: afterTotal,
    total: sum, rounded, roundoff: r2(rounded - sum) }
}
