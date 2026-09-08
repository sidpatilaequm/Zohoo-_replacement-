export const MENU = [
  { group: 'Sales', items: [
    { key: 'invoice', label: 'Customer Invoices', path: '/invoices/new' },
    { key: 'saved',   label: 'Invoice Register',  path: '/invoices' } ] },
  { group: 'Purchases', items: [
    { key: 'po',   label: 'Purchase Orders',  path: '/purchase-orders' },
    { key: 'vinv', label: 'Vendor Invoices',  path: '/vendor-invoices' } ] },
  { group: 'Ordering', trading: true, items: [
    { key: 'so',  label: 'Sales Orders', path: '/sales-orders' },
    { key: 'del', label: 'Deliveries',   path: '/deliveries' } ] },
  { group: 'Inventory', trading: true, items: [
    { key: 'grn',   label: 'Goods Receipt',      path: '/goods-receipt' },
    { key: 'disc',  label: 'Stock Discrepancy',  path: '/discrepancies' },
    { key: 'phys',  label: 'Physical Inventory', path: '/physical-inventory' },
    { key: 'stock', label: 'Stock Report',       path: '/stock' } ] },
  { group: 'Money', items: [
    { key: 'crec', label: 'Customer Payments', path: '/receipts' },
    { key: 'vpay', label: 'Vendor Payments',   path: '/vendor-payments' } ] },
  { group: 'Insight', items: [
    { key: 'reports',   label: 'Reports',       path: '/reports' },
    { key: 'registers', label: 'Registers',     path: '/registers' },
    { key: 'gstr',      label: 'GST Returns',   path: '/gst' } ] },
  { group: 'Masters', items: [
    { key: 'customers', label: 'Customers', path: '/customers' },
    { key: 'vendors',   label: 'Vendors',   path: '/vendors' },
    { key: 'materials', label: 'Materials', path: '/materials' },
    { key: 'attrs',     label: 'Attributes', path: '/attributes' },
    { key: 'hsn',       label: 'HSN and SAC', path: '/hsn' } ] },
  { group: 'Setup', items: [
    { key: 'org',   label: 'Company Information', path: '/company' },
    { key: 'users', label: 'Users and Access',    path: '/users' },
    { key: 'data',  label: 'Templates and Import', path: '/templates' } ] },
]

/** Menus that only make sense for a business holding physical stock. */
export const TRADING_ONLY = new Set(
  MENU.filter(g => g.trading).flatMap(g => g.items.map(i => i.key)))

export const PERM_LABEL = Object.fromEntries(
  MENU.flatMap(g => g.items.map(i => [i.key, i.label])).concat([['data', 'Templates and Import']]))

export const ALL_PERMS = Object.keys(PERM_LABEL)
