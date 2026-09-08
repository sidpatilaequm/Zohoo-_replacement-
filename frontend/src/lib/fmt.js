export const inr = n => Number(n || 0).toLocaleString('en-IN',
  { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const money = n => '₹ ' + inr(n)
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
export const gd = d => {
  if (!d) return '—'
  const x = new Date(d)
  return `${String(x.getDate()).padStart(2, '0')}-${MON[x.getMonth()]}-${x.getFullYear()}`
}
export const today = () => new Date().toISOString().slice(0, 10)
export const initials = n => (n || '').split(/\s+/).slice(0, 2)
  .map(w => w[0] || '').join('').toUpperCase()
