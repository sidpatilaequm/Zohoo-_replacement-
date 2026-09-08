from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (String, Integer, SmallInteger, Numeric, Date, DateTime, Boolean,
                        ForeignKey, Enum, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

PERMS = ["invoice","saved","po","vinv","so","del","grn","disc","phys","stock",
         "crec","vpay","reports","registers","gstr","customers","vendors",
         "materials","attrs","hsn","org","users","data"]

# Only these types are our own goods; consignment belongs to the vendor
# until it is consumed, so it never raises the sellable figure.
OWNED_TYPES = {"NORMAL", "RESERVED", "DAMAGED"}
STOCK_TYPES = ["NORMAL", "RESERVED", "DAMAGED", "CONSIGNMENT"]

class State(Base):
    __tablename__="states"
    code: Mapped[str]=mapped_column(String(2),primary_key=True)
    name: Mapped[str]=mapped_column(String(60))

class Uom(Base):
    __tablename__="uoms"
    code: Mapped[str]=mapped_column(String(6),primary_key=True)
    name: Mapped[str]=mapped_column(String(40))

class Tenant(Base):
    __tablename__="tenants"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    name: Mapped[str]=mapped_column(String(160))
    gstin: Mapped[str|None]=mapped_column(String(15),nullable=True,unique=True)
    pan: Mapped[str|None]=mapped_column(String(10),nullable=True)
    addr: Mapped[str|None]=mapped_column(String(255),nullable=True)
    city: Mapped[str|None]=mapped_column(String(80),nullable=True)
    state_code: Mapped[str]=mapped_column(String(2),ForeignKey("states.code"))
    pin: Mapped[str|None]=mapped_column(String(6),nullable=True)
    company_type: Mapped[str]=mapped_column(
        Enum("TRADING","NONTRADING",name="cotype"),default="NONTRADING")
    logo: Mapped[str|None]=mapped_column(Text,nullable=True)
    inv_prefix: Mapped[str]=mapped_column(String(24),default="INV/")
    inv_seq: Mapped[int]=mapped_column(Integer,default=1)
    po_prefix: Mapped[str]=mapped_column(String(24),default="PO/")
    po_seq: Mapped[int]=mapped_column(Integer,default=1)
    bank: Mapped[str|None]=mapped_column(String(255),nullable=True)
    smtp_from_name: Mapped[str|None]=mapped_column(String(120),nullable=True)
    smtp_from_email: Mapped[str|None]=mapped_column(String(160),nullable=True)
    smtp_reply_to: Mapped[str|None]=mapped_column(String(160),nullable=True)
    smtp_bcc: Mapped[str|None]=mapped_column(String(160),nullable=True)
    smtp_host: Mapped[str|None]=mapped_column(String(160),nullable=True)
    smtp_port: Mapped[int|None]=mapped_column(Integer,nullable=True)
    smtp_encryption: Mapped[str|None]=mapped_column(
        Enum("STARTTLS","SSL","NONE",name="smtp_enc"),nullable=True)
    smtp_username: Mapped[str|None]=mapped_column(String(160),nullable=True)
    smtp_password: Mapped[str|None]=mapped_column(String(255),nullable=True)

class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    name: Mapped[str]=mapped_column(String(120))
    email: Mapped[str]=mapped_column(String(160),unique=True)
    pwd_hash: Mapped[str]=mapped_column(String(255))
    status: Mapped[str]=mapped_column(Enum("ACTIVE","PENDING","DISABLED",name="ustatus"),default="PENDING")
    requested_tenant: Mapped[int|None]=mapped_column(ForeignKey("tenants.id"),nullable=True)
    roles: Mapped[list["UserRole"]]=relationship(back_populates="user",
        cascade="all, delete-orphan",lazy="selectin")

class Group(Base):
    __tablename__="user_groups"
    __table_args__=(UniqueConstraint("tenant_id","name",name="uq_g"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    name: Mapped[str]=mapped_column(String(80))
    perms: Mapped[list["GroupPerm"]]=relationship(back_populates="group",
        cascade="all, delete-orphan",lazy="selectin")

class GroupPerm(Base):
    __tablename__="group_perms"
    group_id: Mapped[int]=mapped_column(ForeignKey("user_groups.id",ondelete="CASCADE"),primary_key=True)
    perm: Mapped[str]=mapped_column(String(32),primary_key=True)
    group: Mapped[Group]=relationship(back_populates="perms")

class UserRole(Base):
    __tablename__="user_roles"
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),primary_key=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"),primary_key=True)
    group_id: Mapped[int]=mapped_column(ForeignKey("user_groups.id"))
    user: Mapped[User]=relationship(back_populates="roles")
    group: Mapped[Group]=relationship(lazy="selectin")
    tenant: Mapped[Tenant]=relationship(lazy="selectin")

class Customer(Base):
    __tablename__="customers"
    __table_args__=(UniqueConstraint("tenant_id","code",name="uq_c"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    code: Mapped[str]=mapped_column(String(20))
    name: Mapped[str]=mapped_column(String(160))
    party_type: Mapped[str]=mapped_column(Enum("B2B","B2C",name="cpt"),default="B2B")
    bill_addr: Mapped[str]=mapped_column(String(255))
    bill_city: Mapped[str]=mapped_column(String(80))
    bill_state: Mapped[str]=mapped_column(String(2),ForeignKey("states.code"))
    bill_pin: Mapped[str|None]=mapped_column(String(6),nullable=True)
    ship_same: Mapped[bool]=mapped_column(Boolean,default=True)
    ship_addr: Mapped[str|None]=mapped_column(String(255),nullable=True)
    ship_city: Mapped[str|None]=mapped_column(String(80),nullable=True)
    ship_state: Mapped[str|None]=mapped_column(String(2),ForeignKey("states.code"),nullable=True)
    ship_pin: Mapped[str|None]=mapped_column(String(6),nullable=True)
    pan: Mapped[str|None]=mapped_column(String(10),nullable=True)
    msme_registered: Mapped[bool]=mapped_column(Boolean,default=False)
    msme_number: Mapped[str|None]=mapped_column(String(30),nullable=True)
    bank_name: Mapped[str|None]=mapped_column(String(120),nullable=True)
    bank_ifsc: Mapped[str|None]=mapped_column(String(11),nullable=True)
    bank_account: Mapped[str|None]=mapped_column(String(30),nullable=True)
    email: Mapped[str|None]=mapped_column(String(160),nullable=True)
    pan: Mapped[str|None]=mapped_column(String(10),nullable=True)
    bank_ifsc: Mapped[str|None]=mapped_column(String(11),nullable=True)
    bank_account: Mapped[str|None]=mapped_column(String(24),nullable=True)
    gstins: Mapped[list["CustomerGstin"]]=relationship(back_populates="customer",
        cascade="all, delete-orphan",lazy="selectin")

class CustomerGstin(Base):
    __tablename__="customer_gstins"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id",ondelete="CASCADE"))
    gstin: Mapped[str]=mapped_column(String(15),unique=True)
    state_code: Mapped[str]=mapped_column(String(2),ForeignKey("states.code"))
    label: Mapped[str|None]=mapped_column(String(80),nullable=True)
    is_default: Mapped[bool]=mapped_column(Boolean,default=False)
    customer: Mapped[Customer]=relationship(back_populates="gstins")

class Vendor(Base):
    __tablename__="vendors"
    __table_args__=(UniqueConstraint("tenant_id","code",name="uq_v"),)

    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    code: Mapped[str]=mapped_column(String(20))
    name: Mapped[str]=mapped_column(String(160))
    party_type: Mapped[str]=mapped_column(
        Enum("B2B","B2C",name="vpt"),default="B2B")
    addr: Mapped[str]=mapped_column(String(255))
    city: Mapped[str]=mapped_column(String(80))
    state_code: Mapped[str]=mapped_column(
        String(2),ForeignKey("states.code"))
    pin: Mapped[str|None]=mapped_column(String(6),nullable=True)

    pan: Mapped[str|None]=mapped_column(String(10),nullable=True)
    msme_registered: Mapped[bool]=mapped_column(Boolean,default=False)
    msme_number: Mapped[str|None]=mapped_column(String(30),nullable=True)
    bank_name: Mapped[str|None]=mapped_column(String(120),nullable=True)
    bank_ifsc: Mapped[str|None]=mapped_column(String(11),nullable=True)
    bank_account: Mapped[str|None]=mapped_column(String(24),nullable=True)
    email: Mapped[str|None]=mapped_column(String(160),nullable=True)
    tds_section: Mapped[str|None]=mapped_column(String(10),nullable=True)
    tds_rate: Mapped[Decimal]=mapped_column(Numeric(5,2),default=0)

    gstins: Mapped[list["VendorGstin"]]=relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
        lazy="selectin")
    
class VendorGstin(Base):
    __tablename__="vendor_gstins"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    vendor_id: Mapped[int]=mapped_column(ForeignKey("vendors.id",ondelete="CASCADE"))
    gstin: Mapped[str]=mapped_column(String(15),unique=True)
    state_code: Mapped[str]=mapped_column(String(2),ForeignKey("states.code"))
    label: Mapped[str|None]=mapped_column(String(80),nullable=True)
    is_default: Mapped[bool]=mapped_column(Boolean,default=False)
    vendor: Mapped[Vendor]=relationship(back_populates="gstins")

class Material(Base):
    __tablename__="materials"
    __table_args__=(UniqueConstraint("tenant_id","code",name="uq_m"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    code: Mapped[str]=mapped_column(String(30))
    descr: Mapped[str]=mapped_column(String(200))
    price: Mapped[Decimal]=mapped_column(Numeric(14,2))
    cost: Mapped[Decimal]=mapped_column(Numeric(14,2),default=0)
    hsn: Mapped[str]=mapped_column(String(8))
    stock_qty: Mapped[Decimal]=mapped_column(Numeric(14,3),default=0)
    uom: Mapped[str]=mapped_column(String(6),ForeignKey("uoms.code"))
    batch_managed: Mapped[bool]=mapped_column(Boolean,default=False)
    shelf_life_days: Mapped[int]=mapped_column(Integer,default=0)
    sgst_pct: Mapped[Decimal]=mapped_column(Numeric(5,2))
    cgst_pct: Mapped[Decimal]=mapped_column(Numeric(5,2))
    igst_pct: Mapped[Decimal]=mapped_column(Numeric(5,2))
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class Invoice(Base):
    __tablename__="invoices"
    __table_args__=(UniqueConstraint("tenant_id","doc_no",name="uq_i"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    doc_no: Mapped[str]=mapped_column(String(40))
    doc_type: Mapped[str]=mapped_column(Enum("TAX","PRO",name="dtype"),default="TAX")
    doc_date: Mapped[date]=mapped_column(Date)
    due_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id"))
    gstin: Mapped[str|None]=mapped_column(String(15),nullable=True)
    pos_state: Mapped[str]=mapped_column(String(2),ForeignKey("states.code"))
    po_no: Mapped[str|None]=mapped_column(String(60),nullable=True)
    po_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    reverse_chg: Mapped[str]=mapped_column(Enum("Y","N",name="rchg"),default="N")
    converted_from: Mapped[str|None]=mapped_column(String(40),nullable=True)
    lines: Mapped[list["InvoiceLine"]]=relationship(back_populates="invoice",
        cascade="all, delete-orphan",lazy="selectin")
    customer: Mapped[Customer]=relationship(lazy="selectin")

class InvoiceLine(Base):
    __tablename__="invoice_lines"
    __table_args__=(UniqueConstraint("invoice_id","line_no",name="uq_il"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    invoice_id: Mapped[int]=mapped_column(ForeignKey("invoices.id",ondelete="CASCADE"))
    line_no: Mapped[int]=mapped_column(SmallInteger)
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    price: Mapped[Decimal]=mapped_column(Numeric(14,2))
    invoice: Mapped[Invoice]=relationship(back_populates="lines")
    material: Mapped[Material]=relationship(lazy="selectin")

class PurchaseOrder(Base):
    __tablename__="purchase_orders"
    __table_args__=(UniqueConstraint("tenant_id","doc_no",name="uq_po"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    doc_no: Mapped[str]=mapped_column(String(40))
    doc_date: Mapped[date]=mapped_column(Date)
    req_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    vendor_id: Mapped[int]=mapped_column(ForeignKey("vendors.id"))
    gstin: Mapped[str|None]=mapped_column(String(15),nullable=True)
    bill_addr: Mapped[str]=mapped_column(Text)
    ship_same: Mapped[bool]=mapped_column(Boolean,default=True)
    ship_addr: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(Enum("OPEN","INVOICED","CANCELLED",name="postat"),default="OPEN")
    lines: Mapped[list["PoLine"]]=relationship(back_populates="po",
        cascade="all, delete-orphan",lazy="selectin")
    vendor: Mapped[Vendor]=relationship(lazy="selectin")

class PoLine(Base):
    __tablename__="po_lines"
    __table_args__=(UniqueConstraint("po_id","line_no",name="uq_pl"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    po_id: Mapped[int]=mapped_column(ForeignKey("purchase_orders.id",ondelete="CASCADE"))
    line_no: Mapped[int]=mapped_column(SmallInteger)
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    price: Mapped[Decimal]=mapped_column(Numeric(14,2))
    po: Mapped[PurchaseOrder]=relationship(back_populates="lines")
    material: Mapped[Material]=relationship(lazy="selectin")

class VendorInvoice(Base):
    __tablename__="vendor_invoices"
    __table_args__=(UniqueConstraint("tenant_id","vendor_id","doc_no",name="uq_vi"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    doc_no: Mapped[str]=mapped_column(String(40))
    doc_date: Mapped[date]=mapped_column(Date)
    due_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    vendor_id: Mapped[int]=mapped_column(ForeignKey("vendors.id"))
    gstin: Mapped[str|None]=mapped_column(String(15),nullable=True)
    po_id: Mapped[int|None]=mapped_column(ForeignKey("purchase_orders.id"),nullable=True)
    lines: Mapped[list["VendorInvoiceLine"]]=relationship(back_populates="vinv",
        cascade="all, delete-orphan",lazy="selectin")
    vendor: Mapped[Vendor]=relationship(lazy="selectin")

class VendorInvoiceLine(Base):
    __tablename__="vendor_invoice_lines"
    __table_args__=(UniqueConstraint("vinv_id","line_no",name="uq_vil"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    vinv_id: Mapped[int]=mapped_column(ForeignKey("vendor_invoices.id",ondelete="CASCADE"))
    line_no: Mapped[int]=mapped_column(SmallInteger)
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    price: Mapped[Decimal]=mapped_column(Numeric(14,2))
    vinv: Mapped[VendorInvoice]=relationship(back_populates="lines")
    material: Mapped[Material]=relationship(lazy="selectin")

class Payment(Base):
    __tablename__="payments"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    pay_type: Mapped[str]=mapped_column(Enum("REC","PAY",name="ptype"))
    pay_date: Mapped[date]=mapped_column(Date)
    invoice_id: Mapped[int|None]=mapped_column(ForeignKey("invoices.id",ondelete="CASCADE"),nullable=True)
    vinv_id: Mapped[int|None]=mapped_column(ForeignKey("vendor_invoices.id",ondelete="CASCADE"),nullable=True)
    amount: Mapped[Decimal]=mapped_column(Numeric(14,2))
    tds: Mapped[Decimal]=mapped_column(Numeric(14,2),default=0)
    mode: Mapped[str]=mapped_column(Enum("NEFT","RTGS","IMPS","UPI","Cheque","Cash","Adjustment",name="pmode"))
    bank_ref: Mapped[str|None]=mapped_column(String(60),nullable=True)
    bank_acct: Mapped[str|None]=mapped_column(String(80),nullable=True)
    narration: Mapped[str|None]=mapped_column(String(200),nullable=True)

# ---------------------------------------------------------- attributes
class Attribute(Base):
    __tablename__="attributes"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    code: Mapped[str]=mapped_column(String(30),unique=True)
    name: Mapped[str]=mapped_column(String(120))
    attr_type: Mapped[str]=mapped_column(
        Enum("LIST","MULTI","TEXT","NUM","DATE",name="atype"))
    values: Mapped[list["AttributeValue"]]=relationship(
        back_populates="attribute",cascade="all, delete-orphan",lazy="selectin")

class AttributeValue(Base):
    __tablename__="attribute_values"
    __table_args__=(UniqueConstraint("attribute_id","value",name="uq_av"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    attribute_id: Mapped[int]=mapped_column(ForeignKey("attributes.id",ondelete="CASCADE"))
    value: Mapped[str]=mapped_column(String(160))
    attribute: Mapped[Attribute]=relationship(back_populates="values")

class MaterialAttribute(Base):
    __tablename__="material_attributes"
    material_id: Mapped[int]=mapped_column(
        ForeignKey("materials.id",ondelete="CASCADE"),primary_key=True)
    attribute_id: Mapped[int]=mapped_column(
        ForeignKey("attributes.id",ondelete="CASCADE"),primary_key=True)
    value: Mapped[str]=mapped_column(String(400))

# --------------------------------------------------------------- stock
class StockLedger(Base):
    __tablename__="stock_ledger"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    move_date: Mapped[date]=mapped_column(Date)
    source: Mapped[str]=mapped_column(Enum("GRN","GI","PI",name="slsrc"))
    doc_no: Mapped[str]=mapped_column(String(40))
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    stock_type: Mapped[str]=mapped_column(
        Enum("NORMAL","RESERVED","DAMAGED","CONSIGNMENT",name="stype"),default="NORMAL")
    batch: Mapped[str|None]=mapped_column(String(40),nullable=True)
    mfg_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    exp_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    po_id: Mapped[int|None]=mapped_column(Integer,nullable=True)
    so_id: Mapped[int|None]=mapped_column(Integer,nullable=True)
    party: Mapped[str|None]=mapped_column(String(160),nullable=True)
    material: Mapped[Material]=relationship(lazy="selectin")

class Discrepancy(Base):
    __tablename__="discrepancies"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    grn_no: Mapped[str]=mapped_column(String(40))
    grn_date: Mapped[date]=mapped_column(Date)
    po_id: Mapped[int]=mapped_column(ForeignKey("purchase_orders.id"))
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    ordered_qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    received_qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    status: Mapped[str]=mapped_column(Enum("HELD","RELEASED",name="dstat"),default="HELD")
    released_on: Mapped[date|None]=mapped_column(Date,nullable=True)
    released_by: Mapped[str|None]=mapped_column(String(120),nullable=True)
    material: Mapped[Material]=relationship(lazy="selectin")

class PhysicalCount(Base):
    __tablename__="physical_counts"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    doc_no: Mapped[str]=mapped_column(String(40))
    count_date: Mapped[date]=mapped_column(Date)
    counted_by: Mapped[str|None]=mapped_column(String(120),nullable=True)
    reason: Mapped[str|None]=mapped_column(String(200),nullable=True)
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    batch: Mapped[str|None]=mapped_column(String(40),nullable=True)
    stock_type: Mapped[str]=mapped_column(
        Enum("NORMAL","RESERVED","DAMAGED","CONSIGNMENT",name="pcstype"))
    book_qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    counted_qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    diff_qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    material: Mapped[Material]=relationship(lazy="selectin")

# ------------------------------------------------------------ ordering
class SalesOrder(Base):
    __tablename__="sales_orders"
    __table_args__=(UniqueConstraint("tenant_id","doc_no",name="uq_so"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    doc_no: Mapped[str]=mapped_column(String(40))
    doc_date: Mapped[date]=mapped_column(Date)
    req_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id"))
    cust_ref: Mapped[str|None]=mapped_column(String(60),nullable=True)
    lines: Mapped[list["SoLine"]]=relationship(back_populates="so",
        cascade="all, delete-orphan",lazy="selectin")
    customer: Mapped[Customer]=relationship(lazy="selectin")

class SoLine(Base):
    __tablename__="so_lines"
    __table_args__=(UniqueConstraint("so_id","line_no",name="uq_sol"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    so_id: Mapped[int]=mapped_column(ForeignKey("sales_orders.id",ondelete="CASCADE"))
    line_no: Mapped[int]=mapped_column(SmallInteger)
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    price: Mapped[Decimal]=mapped_column(Numeric(14,2))
    so: Mapped[SalesOrder]=relationship(back_populates="lines")
    material: Mapped[Material]=relationship(lazy="selectin")

class Delivery(Base):
    __tablename__="deliveries"
    __table_args__=(UniqueConstraint("tenant_id","doc_no",name="uq_dl"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    doc_no: Mapped[str]=mapped_column(String(40))
    doc_date: Mapped[date]=mapped_column(Date)
    so_id: Mapped[int]=mapped_column(ForeignKey("sales_orders.id"))
    ship_to: Mapped[str|None]=mapped_column(String(400),nullable=True)
    lines: Mapped[list["DeliveryLine"]]=relationship(back_populates="delivery",
        cascade="all, delete-orphan",lazy="selectin")
    so: Mapped[SalesOrder]=relationship(lazy="selectin")

class DeliveryLine(Base):
    __tablename__="delivery_lines"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    delivery_id: Mapped[int]=mapped_column(ForeignKey("deliveries.id",ondelete="CASCADE"))
    material_id: Mapped[int]=mapped_column(ForeignKey("materials.id"))
    batch: Mapped[str|None]=mapped_column(String(40),nullable=True)
    stock_type: Mapped[str]=mapped_column(
        Enum("NORMAL","RESERVED","DAMAGED","CONSIGNMENT",name="dlstype"),default="NORMAL")
    exp_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    qty: Mapped[Decimal]=mapped_column(Numeric(14,3))
    delivery: Mapped[Delivery]=relationship(back_populates="lines")
    material: Mapped[Material]=relationship(lazy="selectin")

# ------------------------------------------------------- shared masters
class Designation(Base):
    __tablename__="designations"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    name: Mapped[str]=mapped_column(String(80),unique=True)

class Bank(Base):
    __tablename__="banks"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    name: Mapped[str]=mapped_column(String(120),unique=True)
    short_code: Mapped[str|None]=mapped_column(String(12),nullable=True)

class HsnCode(Base):
    __tablename__="hsn_codes"
    __table_args__=(UniqueConstraint("tenant_id","code",name="uq_h"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    code: Mapped[str]=mapped_column(String(8))
    descr: Mapped[str]=mapped_column(String(200))
    kind: Mapped[str]=mapped_column(Enum("HSN","SAC",name="hkind"),default="HSN")
    sgst_pct: Mapped[Decimal]=mapped_column(Numeric(5,2))
    cgst_pct: Mapped[Decimal]=mapped_column(Numeric(5,2))
    igst_pct: Mapped[Decimal]=mapped_column(Numeric(5,2))
    cess_pct: Mapped[Decimal]=mapped_column(Numeric(5,2),default=0)
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class PartyContact(Base):
    __tablename__="party_contacts"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    party_kind: Mapped[str]=mapped_column(Enum("CUSTOMER","VENDOR",name="pkind"))
    party_id: Mapped[int]=mapped_column(Integer)
    first_name: Mapped[str]=mapped_column(String(60))
    middle_name: Mapped[str|None]=mapped_column(String(60),nullable=True)
    last_name: Mapped[str|None]=mapped_column(String(60),nullable=True)
    designation_id: Mapped[int|None]=mapped_column(
        ForeignKey("designations.id"),nullable=True)
    phone: Mapped[str|None]=mapped_column(String(20),nullable=True)
    email: Mapped[str|None]=mapped_column(String(160),nullable=True)
    is_primary: Mapped[bool]=mapped_column(Boolean,default=False)
    designation: Mapped[Designation|None]=relationship(lazy="selectin")

class Gstr3bUpload(Base):
    __tablename__="gstr3b_uploads"
    __table_args__=(UniqueConstraint("tenant_id","period",name="uq_g3"),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    tenant_id: Mapped[int]=mapped_column(ForeignKey("tenants.id",ondelete="CASCADE"))
    period: Mapped[str]=mapped_column(String(7))
    uploaded_by: Mapped[str|None]=mapped_column(String(120),nullable=True)
    out_taxable: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
    out_igst: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
    out_cgst: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
    out_sgst: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
    itc_igst: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
    itc_cgst: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
    itc_sgst: Mapped[Decimal]=mapped_column(Numeric(16,2),default=0)
