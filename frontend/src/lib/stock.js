export const STOCK_TYPES = [
  { code: 'NORMAL',      label: 'Normal',      kind: 'ok',   owned: true,
    note: 'Available to sell' },
  { code: 'RESERVED',    label: 'Reserved',    kind: 'warn', owned: true,
    note: 'Committed to an order, not available' },
  { code: 'DAMAGED',     label: 'Damaged',     kind: 'bad',  owned: true,
    note: 'Held back, not saleable' },
  { code: 'CONSIGNMENT', label: 'Consignment', kind: 'no',   owned: false,
    note: 'On our premises but owned by the vendor until consumed' },
]
export const stockMeta = c => STOCK_TYPES.find(t => t.code === c) || STOCK_TYPES[0]

/** Expiry is the manufacturing date plus the shelf life, nothing cleverer. */
export function expiryFrom(mfg, shelfDays) {
  if (!mfg || !shelfDays) return ''
  const d = new Date(mfg)
  if (isNaN(d)) return ''
  d.setDate(d.getDate() + Number(shelfDays))
  return d.toISOString().slice(0, 10)
}
export const daysLeft = exp => exp
  ? Math.round((new Date(exp) - new Date(new Date().toISOString().slice(0, 10))) / 86400000)
  : null
