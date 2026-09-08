import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { MENU, TRADING_ONLY } from './lib/menu'
import Shell from './components/Shell'
import { Loading } from './components/ui'
import Auth from './pages/Auth'
import Customers from './pages/Customers'
import Vendors from './pages/Vendors'
import Materials from './pages/Materials'
import NewInvoice from './pages/NewInvoice'
import Invoices from './pages/Invoices'
import PurchaseOrders from './pages/PurchaseOrders'
import VendorInvoices from './pages/VendorInvoices'
import Receipts from './pages/Receipts'
import VendorPayments from './pages/VendorPayments'
import Reports from './pages/Reports'
import GstReturns from './pages/GstReturns'
import Company from './pages/Company'
import Users from './pages/Users'
import Attributes from './pages/Attributes'
import SalesOrders from './pages/SalesOrders'
import Deliveries from './pages/Deliveries'
import GoodsReceipt from './pages/GoodsReceipt'
import Discrepancies from './pages/Discrepancies'
import PhysicalInventory from './pages/PhysicalInventory'
import StockReport from './pages/StockReport'
import HsnCodes from './pages/HsnCodes'
import Registers from './pages/Registers'
import Templates from './pages/Templates'

const PAGES = {
  invoice: NewInvoice, saved: Invoices, po: PurchaseOrders, vinv: VendorInvoices,
  crec: Receipts, vpay: VendorPayments, reports: Reports, gstr: GstReturns,
  customers: Customers, vendors: Vendors, materials: Materials,
  org: Company, users: Users, attrs: Attributes,
  so: SalesOrders, del: Deliveries, grn: GoodsReceipt, disc: Discrepancies,
  phys: PhysicalInventory, stock: StockReport,
  hsn: HsnCodes, registers: Registers, data: Templates,
}

export default function App() {
  const { session, me, loading, can } = useAuth()
  if (!session) return <Auth />
  if (loading || !me) return <div className="center"><Loading /></div>

  const trading = me?.tenant?.company_type === 'TRADING'
  const reachable = k => can(k) && !(TRADING_ONLY.has(k) && !trading)
  const allowed = MENU.flatMap(g => g.items).filter(i => reachable(i.key))
  const home = allowed[0]?.path || '/no-access'

  return (
    <Shell>
      <Routes>
        {MENU.flatMap(g => g.items).map(i => {
          const P = PAGES[i.key]
          return <Route key={i.key} path={i.path}
            element={reachable(i.key) ? <P /> : <Navigate to={home} replace />} />
        })}
        <Route path="/no-access" element={
          <div className="alert warn">Your group has not been given access to any screen.
            Ask an administrator of this organisation to change your group.</div>} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Shell>
  )
}
