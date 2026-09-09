const BASE = import.meta.env.VITE_API_URL || '/api'

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

function readDetail(data, fallback) {
  const d = data && data.detail
  if (Array.isArray(d)) return d.map(x => x.msg || JSON.stringify(x)).join('; ')
  if (typeof d === 'string') return d
  return fallback
}

export async function req(path, { method = 'GET', body, token, tenantId } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  if (tenantId) headers['X-Tenant-Id'] = String(tenantId)
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError('Cannot reach the API. Is the backend running on port 8000?', 0)
  }
  if (res.status === 204) return null
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) throw new ApiError(readDetail(data, res.statusText), res.status)
  return data
}

export function makeApi(token, tenantId) {
  const call = (p, o = {}) => req(p, { ...o, token, tenantId })
  return {
    me:            ()   => call('/auth/me'),
    states:        ()   => call('/states'),
    uoms:          ()   => call('/uoms'),
    perms:         ()   => call('/perms'),

    customers:     ()   => call('/customers'),
    addCustomer:   (b)  => call('/customers', { method: 'POST', body: b }),
    delCustomer:   (id) => call(`/customers/${id}`, { method: 'DELETE' }),

    vendors:       ()   => call('/vendors'),
    addVendor:     (b)  => call('/vendors', { method: 'POST', body: b }),
    delVendor:     (id) => call(`/vendors/${id}`, { method: 'DELETE' }),

    materials:     ()   => call('/materials'),
    addMaterial:   (b)  => call('/materials', { method: 'POST', body: b }),
    delMaterial:   (id) => call(`/materials/${id}`, { method: 'DELETE' }),

    invoices:      ()   => call('/invoices'),
    invoice:       (id) => call(`/invoices/${id}`),
    addInvoice:    (b)  => call('/invoices', { method: 'POST', body: b }),
    convert:       (id) => call(`/invoices/${id}/convert`, { method: 'POST' }),
    cancelInvoice: (id, reason) => call(`/invoices/${id}/cancel`, { method: 'POST', body: { reason } }),
    delInvoice:    (id) => call(`/invoices/${id}`, { method: 'DELETE' }),

    pos:           ()   => call('/purchase-orders'),
    addPo:         (b)  => call('/purchase-orders', { method: 'POST', body: b }),

    vinvs:         ()   => call('/vendor-invoices'),
    addVinv:       (b)  => call('/vendor-invoices', { method: 'POST', body: b }),
    extractCaps:   ()   => call('/vendor-invoices/extract/capabilities'),
    extractVinv:   (f)  => upload('/vendor-invoices/extract', f, { token, tenantId }),

    // ---- PDF print-outs (variant: TRADING | NONTRADING, defaults to the org's type) ----
    printVariants: ()   => call('/print/variants'),
    printPdf:      (kind, id, variant, inline, extra = '') => download(
                        `/print/${kind}/${id}.pdf?variant=${variant || ''}`
                        + (inline ? '&disposition=inline' : '') + extra, { token, tenantId }, inline),

    receipts:      ()   => call('/receipts'),
    addReceipt:    (b)  => call('/receipts', { method: 'POST', body: b }),
    vendorPayments:()   => call('/vendor-payments'),
    addVendorPay:  (b)  => call('/vendor-payments', { method: 'POST', body: b }),
    delPayment:    (id) => call(`/payments/${id}`, { method: 'DELETE' }),

    org:           ()   => call('/org'),
    saveOrg:       (b)  => call('/org', { method: 'PUT', body: b }),
    saveLogo:      (l)  => call('/org/logo', { method: 'PUT', body: { logo: l } }),
    saveSmtp:      (b)  => call('/org/smtp', { method: 'PUT', body: b }),
    checkSmtp:     ()   => call('/org/smtp/check', { method: 'POST' }),

    groups:        ()   => call('/groups'),
    addGroup:      (b)  => call('/groups', { method: 'POST', body: b }),
    editGroup:     (id, b) => call(`/groups/${id}`, { method: 'PUT', body: b }),
    delGroup:      (id) => call(`/groups/${id}`, { method: 'DELETE' }),
    users:         ()   => call('/users'),
    addUser:       (b)  => call('/users', { method: 'POST', body: b }),
    setRole:       (id, gid) => call(`/users/${id}/role`,
                        { method: 'PUT', body: { user_id: id, group_id: gid } }),
    rejectPending: (id) => call(`/users/${id}/pending`, { method: 'DELETE' }),

    periods:       ()   => call('/returns/periods'),
    gstr1:         (p)  => call(`/returns/gstr1?period=${p}`),
    gstr3b:        (p)  => call(`/returns/gstr3b?period=${p}`),
    recon:         (p)  => call(`/returns/reconciliation?period=${p}`),
    reconAB:       (p)  => call(`/returns/reconciliation/ab?period=${p}`),
    gstr1Portal:   (p, fmt) => download(`/returns/gstr1/portal.${fmt}?period=${p}`, { token, tenantId }),
    gstr1SectionCsv: (s, p) => download(`/returns/gstr1/${s}.csv?period=${p}`, { token, tenantId }),
    upload3bJson:  (p, f) => upload(`/registers/gstr3b/upload-json?period=${p}`, f, { token, tenantId }),
    upload3bCsv:   (p, f) => upload(`/registers/gstr3b/upload-csv?period=${p}`, f, { token, tenantId }),
    receivables:   ()   => call('/returns/reports/receivables'),
    payables:      ()   => call('/returns/reports/payables'),
    margin:        ()   => call('/returns/reports/margin'),
    csvUrl:        (s, p) => `${BASE}/returns/gstr1/${s}.csv?period=${p}`,

    // ---- reference masters ----
    designations:  ()   => call('/designations'),
    addDesignation:(b)  => call('/designations', { method: 'POST', body: b }),
    banks:         ()   => call('/banks'),
    addBank:       (b)  => call('/banks', { method: 'POST', body: b }),
    hsn:           ()   => call('/hsn'),
    addHsn:        (b)  => call('/hsn', { method: 'POST', body: b }),
    editHsn:       (id, b) => call(`/hsn/${id}`, { method: 'PUT', body: b }),
    delHsn:        (id) => call(`/hsn/${id}`, { method: 'DELETE' }),

    // ---- attributes ----
    attributes:    ()   => call('/attributes'),
    addAttribute:  (b)  => call('/attributes', { method: 'POST', body: b }),
    editAttribute: (id, b) => call(`/attributes/${id}`, { method: 'PUT', body: b }),
    delAttribute:  (id) => call(`/attributes/${id}`, { method: 'DELETE' }),

    // ---- inventory ----
    openPos:       ()   => call('/grn/open-pos'),
    postGrn:       (b)  => call('/grn', { method: 'POST', body: b }),
    discrepancies: (st) => call('/discrepancies' + (st ? `?status=${st}` : '')),
    releaseDisc:   (id) => call(`/discrepancies/${id}/release`, { method: 'POST' }),
    holdDisc:      (id) => call(`/discrepancies/${id}/hold`, { method: 'POST' }),
    discInvoiceable: () => call('/discrepancies/invoiceable'),
    countSheet:    ()   => call('/physical/sheet'),
    postCount:     (b)  => call('/physical', { method: 'POST', body: b }),
    counts:        ()   => call('/physical'),
    stockSummary:  ()   => call('/stock/summary'),
    stockBatches:  ()   => call('/stock/batches'),
    stockMoves:    ()   => call('/stock/movements'),

    // ---- ordering ----
    salesOrders:   ()   => call('/sales-orders'),
    addSalesOrder: (b)  => call('/sales-orders', { method: 'POST', body: b }),
    delSalesOrder: (id) => call(`/sales-orders/${id}`, { method: 'DELETE' }),
    suggestPicks:  (id) => call(`/deliveries/suggest/${id}`),
    postDelivery:  (b)  => call('/deliveries', { method: 'POST', body: b }),
    deliveries:    ()   => call('/deliveries'),

    // ---- registers and GST reconciliation ----
    invoiceRegister: (p) => call('/registers/invoices' + (p ? `?period=${p}` : '')),
    gstRegister:     (p) => call('/registers/gst' + (p ? `?period=${p}` : '')),
    tdsRegister:     (p) => call('/registers/tds' + (p ? `?period=${p}` : '')),
    registerCsv:  (w, p) => `${BASE}/registers/${w}.csv` + (p ? `?period=${p}` : ''),
    upload3b:      (b)  => call('/registers/gstr3b', { method: 'POST', body: b }),
    compare3b:     (p)  => call(`/registers/gstr3b/compare?period=${p}`),
    template3bUrl: ()   => `${BASE}/registers/gstr3b/template.csv`,

    // ---- master data templates ----
    templates:     ()   => call('/templates'),
    templateUrl:   (k)  => `${BASE}/templates/${k}.csv`,
    importCsv:  (k, text) => call(`/templates/${k}/import`,
                    { method: 'POST', body: { csv: text } }),

  }
}

export const signIn = (email, password) =>
  req('/auth/signin', { method: 'POST', body: { email, password } })
export const signUp = (body) => req('/auth/signup', { method: 'POST', body })
export const openTenants = () => req('/auth/tenants')

/** Fetch a binary (PDF) with the auth headers and hand it to the browser:
 *  inline=true opens it in a new tab, otherwise it is downloaded with the
 *  server's filename. Plain <a href> cannot carry the bearer token. */
export async function download(path, { token, tenantId } = {}, inline = false) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (tenantId) headers['X-Tenant-Id'] = String(tenantId)
  const res = await fetch(BASE + path, { headers })
  if (!res.ok) {
    let msg = res.statusText
    try { msg = readDetail(JSON.parse(await res.text()), msg) } catch { /* not json */ }
    throw new ApiError(msg, res.status)
  }
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') || ''
  const m = /filename="?([^";]+)"?/.exec(cd)
  const name = m ? m[1] : 'document.pdf'
  const url = URL.createObjectURL(blob)
  if (inline) {
    window.open(url, '_blank', 'noopener')
  } else {
    const a = document.createElement('a')
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove()
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000)
  return name
}

/** Multipart upload; the JSON helper cannot carry a file. */
export async function upload(path, file, { token, tenantId } = {}) {
  const fd = new FormData()
  fd.append('file', file)
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (tenantId) headers['X-Tenant-Id'] = String(tenantId)
  const res = await fetch(BASE + path, { method: 'POST', headers, body: fd })
  const text = await res.text()
  let data; try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const d = data && data.detail
    throw new ApiError(Array.isArray(d) ? d.map(x => x.msg || x).join('; ')
      : (typeof d === 'string' ? d : res.statusText), res.status)
  }
  return data
}
