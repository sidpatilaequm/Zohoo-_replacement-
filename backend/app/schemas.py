from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'


class SignUp(BaseModel):
    name: str
    email: str
    password: str
    mode: str = "new"                 # "new" | "join"
    org_name: str | None = None
    org_gstin: str | None = None
    org_state: str = "29"
    join_tenant_id: int | None = None

    @model_validator(mode="after")
    def _v(self):
        import re
        if not self.name.strip():
            raise ValueError("Enter your name")
        if not re.match(EMAIL, self.email):
            raise ValueError("Enter a valid email address")
        if len(self.password) < 8:
            raise ValueError("Use a password of at least 8 characters")
        if self.mode == "new":
            if not (self.org_name or "").strip():
                raise ValueError("Enter the organisation name")
            if self.org_gstin and len(self.org_gstin) != 15:
                raise ValueError("A GSTIN is exactly 15 characters")
            if self.org_gstin and self.org_gstin[:2] != self.org_state:
                raise ValueError("The GSTIN state code and the state selected disagree")
        elif not self.join_tenant_id:
            raise ValueError("Choose the organisation you want to join")
        return self


class SignIn(BaseModel):
    email: str
    password: str


class GstinIn(BaseModel):
    gstin: str
    label: str | None = None
    is_default: bool = False

    @field_validator("gstin")
    @classmethod
    def _g(cls, v):
        v = v.strip().upper()
        if len(v) != 15:
            raise ValueError("A GSTIN is exactly 15 characters")
        if not v[:2].isdigit():
            raise ValueError("A GSTIN begins with a two-digit state code")
        return v


class ContactIn(BaseModel):
    first_name: str
    middle_name: str | None = None
    last_name: str | None = None
    designation_id: int | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool = False

    @model_validator(mode="after")
    def _check_contact(self):
        import re
        if not self.first_name.strip():
            raise ValueError("A contact needs at least a first name")
        if self.email and not re.match(EMAIL, self.email):
            raise ValueError(f"{self.email} is not a valid email address")
        if self.phone and not re.fullmatch(r"[0-9 +()\-]{6,20}", self.phone):
            raise ValueError(f"{self.phone} does not look like a phone number")
        return self


class BankIn(BaseModel):
    bank_name: str | None = None
    bank_ifsc: str | None = None
    bank_account: str | None = None

    @model_validator(mode="after")
    def _check_bank(self):
        import re
        if self.bank_ifsc:
            self.bank_ifsc = self.bank_ifsc.strip().upper()
            # four letters, a zero, then six alphanumerics
            if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", self.bank_ifsc):
                raise ValueError(
                    f"{self.bank_ifsc} is not a valid IFSC. It is 11 characters: four letters, "
                    "a zero, then six more.")
        if self.bank_account:
            self.bank_account = self.bank_account.strip().replace(" ", "")
            if not re.fullmatch(r"[0-9A-Za-z]{5,30}", self.bank_account):
                raise ValueError(
                    f"{self.bank_account!r} is not a usable account number. Indian account "
                    "numbers run from 5 to 30 characters with no spaces or punctuation.")
        if (self.bank_ifsc or self.bank_account) and not self.bank_name:
            raise ValueError("Choose the bank name as well")
        return self


class PanMsmeIn(BaseModel):
    pan: str | None = None
    msme_registered: bool = False
    msme_number: str | None = None

    @model_validator(mode="after")
    def _check_pan(self):
        import re
        if self.pan:
            self.pan = self.pan.strip().upper()
            if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", self.pan):
                raise ValueError(
                    f"{self.pan} is not a valid PAN. It is ten characters: five letters, "
                    "four digits, then a letter.")
        if self.msme_registered and not (self.msme_number or "").strip():
            raise ValueError("Give the Udyam or MSME registration number")
        return self


class CustomerIn(BankIn, PanMsmeIn):
    code: str | None = None
    name: str
    party_type: str = "B2B"
    bill_addr: str
    bill_city: str
    bill_state: str
    bill_pin: str | None = None
    ship_same: bool = True
    ship_addr: str | None = None
    ship_city: str | None = None
    ship_state: str | None = None
    ship_pin: str | None = None
    email: str | None = None
    gstins: list[GstinIn] = []
    contacts: list[ContactIn] = []

    @model_validator(mode="after")
    def _cust(self):
        if self.party_type == "B2B" and not self.gstins:
            raise ValueError("A B2B customer needs at least one GSTIN")
        if self.party_type == "B2C" and self.gstins:
            raise ValueError("A B2C customer cannot hold a GSTIN")
        if not self.ship_same and not (self.ship_addr and self.ship_state):
            raise ValueError("A separate delivery address needs an address and a state")
        return self


class VendorIn(BankIn, PanMsmeIn):
    code: str | None = None
    name: str
    party_type: str = "B2B"
    tds_section: str | None = None
    tds_rate: Decimal = Decimal("0")
    addr: str
    city: str
    state_code: str
    pin: str | None = None
    email: str | None = None
    gstins: list[GstinIn] = []
    contacts: list[ContactIn] = []

    @model_validator(mode="after")
    def _vend(self):
        if self.party_type == "B2B" and not self.gstins:
            raise ValueError("A registered vendor needs at least one GSTIN")
        if self.party_type == "B2C" and self.gstins:
            raise ValueError("An unregistered vendor cannot hold a GSTIN")
        return self

    @model_validator(mode="after")
    def _v_tds(self):
        if self.tds_rate < 0 or self.tds_rate > 100:
            raise ValueError("A TDS rate is a percentage between 0 and 100")
        if self.tds_rate and not self.tds_section:
            raise ValueError("Give the TDS section as well as the rate, for example 194C")
        return self



class MaterialIn(BaseModel):
    code: str
    descr: str
    price: Decimal
    cost: Decimal = Decimal("0")
    hsn: str
    stock_qty: Decimal = Decimal("0")
    uom: str = "NOS"
    batch_managed: bool = False
    shelf_life_days: int = 0
    sgst_pct: Decimal | None = None
    cgst_pct: Decimal | None = None
    igst_pct: Decimal | None = None
    use_hsn_rates: bool = True
    attributes: dict[str, str] = {}

    @model_validator(mode="after")
    def _v(self):
        given = [self.sgst_pct, self.cgst_pct, self.igst_pct]
        if any(x is not None for x in given):
            if any(x is None for x in given):
                raise ValueError("Give all three rates, or none and let the HSN master supply them")
            if abs(self.sgst_pct + self.cgst_pct - self.igst_pct) > Decimal("0.005"):
                raise ValueError(f"SGST {self.sgst_pct}% plus CGST {self.cgst_pct}% is "
                                 f"{self.sgst_pct + self.cgst_pct}%, which does not equal "
                                 f"IGST {self.igst_pct}%")
        if self.price < 0 or self.cost < 0:
            raise ValueError("Price and cost cannot be negative")
        if self.shelf_life_days < 0:
            raise ValueError("Shelf life cannot be negative")
        return self


class LineIn(BaseModel):
    material_id: int
    qty: Decimal = Field(gt=0)
    price: Decimal | None = None


class InvoiceIn(BaseModel):
    doc_no: str | None = None
    doc_type: str = "TAX"
    doc_date: date
    due_date: date | None = None
    customer_id: int
    gstin: str | None = None
    pos_state: str | None = None
    po_no: str | None = None
    po_date: date | None = None
    reverse_chg: str = "N"
    lines: list[LineIn]

    @model_validator(mode="after")
    def _v(self):
        if self.doc_type not in ("TAX", "PRO"):
            raise ValueError("doc_type must be TAX or PRO")
        if not self.lines:
            raise ValueError("An invoice needs at least one line")
        if self.po_date and self.po_date > self.doc_date:
            raise ValueError("PO date cannot be after the invoice date")
        if self.due_date and self.due_date < self.doc_date:
            raise ValueError("Due date cannot be before the invoice date")
        return self


class PoIn(BaseModel):
    doc_no: str | None = None
    doc_date: date
    req_date: date | None = None
    vendor_id: int
    gstin: str | None = None
    bill_addr: str | None = None
    ship_same: bool = True
    ship_addr: str | None = None
    lines: list[LineIn]

    @model_validator(mode="after")
    def _v(self):
        if not self.lines:
            raise ValueError("A purchase order needs at least one line")
        if self.req_date and self.req_date < self.doc_date:
            raise ValueError("Required-by date cannot be before the PO date")
        if not self.ship_same and not self.ship_addr:
            raise ValueError("Give the delivery address")
        return self


class VendorInvoiceIn(BaseModel):
    doc_no: str
    doc_date: date
    due_date: date | None = None
    po_id: int | None = None
    vendor_id: int | None = None
    gstin: str | None = None
    lines: list[LineIn] | None = None

    @model_validator(mode="after")
    def _v(self):
        if not self.po_id and not (self.vendor_id and self.lines):
            raise ValueError("Give a purchase order, or a vendor with lines")
        return self


class PaymentIn(BaseModel):
    pay_type: str
    pay_date: date
    invoice_id: int | None = None
    vinv_id: int | None = None
    amount: Decimal = Field(gt=0)
    tds: Decimal = Decimal("0")
    mode: str = "NEFT"
    bank_ref: str | None = None
    bank_acct: str | None = None
    narration: str | None = None

    @model_validator(mode="after")
    def _v(self):
        if self.pay_type == "REC" and (not self.invoice_id or self.vinv_id):
            raise ValueError("A receipt settles a customer invoice only")
        if self.pay_type == "PAY" and (not self.vinv_id or self.invoice_id):
            raise ValueError("A payment settles a vendor invoice only")
        return self


class TenantIn(BaseModel):
    name: str
    company_type: str = "NONTRADING"
    gstin: str | None = None
    pan: str | None = None
    addr: str | None = None
    city: str | None = None
    state_code: str
    pin: str | None = None
    inv_prefix: str = "INV/"
    inv_seq: int = 1
    po_prefix: str = "PO/"
    po_seq: int = 1
    bank: str | None = None

    @model_validator(mode="after")
    def _v(self):
        if self.company_type not in ("TRADING", "NONTRADING"):
            raise ValueError("company_type must be TRADING or NONTRADING")
        if self.gstin:
            if len(self.gstin) != 15:
                raise ValueError("A GSTIN is exactly 15 characters")
            if self.gstin[:2] != self.state_code:
                raise ValueError(f"GSTIN begins {self.gstin[:2]} but the state is {self.state_code}")
        return self


class SmtpIn(BaseModel):
    from_name: str | None = None
    from_email: str | None = None
    reply_to: str | None = None
    bcc: str | None = None
    host: str | None = None
    port: int | None = None
    encryption: str | None = "STARTTLS"
    username: str | None = None
    password: str | None = None

    @model_validator(mode="after")
    def _v(self):
        import re
        if self.from_email and not re.match(EMAIL, self.from_email):
            raise ValueError("The send-from address is not a valid email address")
        if self.host and not self.port:
            raise ValueError("Give the SMTP port as well as the host")
        if self.port and not (1 <= self.port <= 65535):
            raise ValueError("That port number is out of range")
        return self


class GroupIn(BaseModel):
    name: str
    perms: list[str]

    @model_validator(mode="after")
    def _v(self):
        from .models import PERMS
        if not self.name.strip():
            raise ValueError("Give the group a name")
        bad = [p for p in self.perms if p not in PERMS]
        if bad:
            raise ValueError(f"Unknown permission: {', '.join(bad)}")
        if not self.perms:
            raise ValueError("Give the group at least one menu")
        return self


class UserRoleIn(BaseModel):
    user_id: int
    group_id: int | None = None       # None removes access to this tenant

# ------------------------------------------------------------ inventory
class AttributeIn(BaseModel):
    code: str
    name: str
    attr_type: str
    values: list[str] = []

    @model_validator(mode="after")
    def _v(self):
        if self.attr_type not in ("LIST", "MULTI", "TEXT", "NUM", "DATE"):
            raise ValueError("attr_type must be LIST, MULTI, TEXT, NUM or DATE")
        if not self.code.strip() or not self.name.strip():
            raise ValueError("Code and name are both required")
        if self.attr_type in ("LIST", "MULTI") and not self.values:
            raise ValueError("A dropdown or multiple-choice attribute needs at least one value")
        if self.attr_type not in ("LIST", "MULTI") and self.values:
            raise ValueError("Only a dropdown or multiple-choice attribute holds values")
        return self


STOCK_TYPE_SET = {"NORMAL", "RESERVED", "DAMAGED", "CONSIGNMENT"}


class GrnLineIn(BaseModel):
    material_id: int
    qty: Decimal
    stock_type: str = "NORMAL"
    batch: str | None = None
    mfg_date: date | None = None
    exp_date: date | None = None

    @model_validator(mode="after")
    def _v(self):
        if self.stock_type not in STOCK_TYPE_SET:
            raise ValueError(f"stock_type must be one of {', '.join(sorted(STOCK_TYPE_SET))}")
        if self.qty < 0:
            raise ValueError("Quantity cannot be negative")
        return self


class GrnIn(BaseModel):
    doc_no: str
    doc_date: date
    po_id: int
    delivery_note: str | None = None
    lines: list[GrnLineIn]

    @model_validator(mode="after")
    def _v(self):
        if not self.doc_no.strip():
            raise ValueError("A receipt number is required")
        if not self.lines:
            raise ValueError("A receipt needs at least one line")
        return self


class PhysLineIn(BaseModel):
    material_id: int
    batch: str | None = None
    stock_type: str = "NORMAL"
    counted_qty: Decimal = Field(ge=0)


class PhysIn(BaseModel):
    doc_no: str
    count_date: date
    counted_by: str | None = None
    reason: str | None = None
    lines: list[PhysLineIn]

    @model_validator(mode="after")
    def _v(self):
        if not self.doc_no.strip():
            raise ValueError("A count document number is required")
        if not self.lines:
            raise ValueError("Nothing has been counted")
        return self


class SoLineIn(BaseModel):
    material_id: int
    qty: Decimal = Field(gt=0)
    price: Decimal | None = None


class SalesOrderIn(BaseModel):
    doc_no: str | None = None
    doc_date: date
    req_date: date | None = None
    customer_id: int
    cust_ref: str | None = None
    lines: list[SoLineIn]

    @model_validator(mode="after")
    def _v(self):
        if not self.lines:
            raise ValueError("A sales order needs at least one line")
        if self.req_date and self.req_date < self.doc_date:
            raise ValueError("Required-by date cannot be before the order date")
        return self


class PickIn(BaseModel):
    material_id: int
    batch: str | None = None
    stock_type: str = "NORMAL"
    qty: Decimal = Field(gt=0)


class DeliveryIn(BaseModel):
    doc_no: str | None = None
    doc_date: date
    so_id: int
    ship_to: str | None = None
    picks: list[PickIn]

    @model_validator(mode="after")
    def _v(self):
        if not self.picks:
            raise ValueError("Pick some stock first")
        return self

# ---------------------------------------------------------- new masters
class HsnIn(BaseModel):
    code: str
    descr: str
    kind: str = "HSN"
    sgst_pct: Decimal
    cgst_pct: Decimal
    igst_pct: Decimal
    cess_pct: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _v(self):
        if self.kind not in ("HSN", "SAC"):
            raise ValueError("kind must be HSN or SAC")
        if abs(self.sgst_pct + self.cgst_pct - self.igst_pct) > Decimal("0.005"):
            raise ValueError(f"SGST {self.sgst_pct}% plus CGST {self.cgst_pct}% is "
                             f"{self.sgst_pct + self.cgst_pct}%, which does not equal "
                             f"IGST {self.igst_pct}%")
        if not (0 <= self.igst_pct <= 40):
            raise ValueError("That GST rate is outside the range 0 to 40 percent")
        if not self.code.strip():
            raise ValueError("An HSN or SAC code is required")
        return self


class NamedIn(BaseModel):
    name: str
    short_code: str | None = None

    @model_validator(mode="after")
    def _v(self):
        if not self.name.strip():
            raise ValueError("A name is required")
        return self


class Gstr3bIn(BaseModel):
    period: str
    out_taxable: Decimal = Decimal("0")
    out_igst: Decimal = Decimal("0")
    out_cgst: Decimal = Decimal("0")
    out_sgst: Decimal = Decimal("0")
    itc_igst: Decimal = Decimal("0")
    itc_cgst: Decimal = Decimal("0")
    itc_sgst: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _v(self):
        import re
        if not re.fullmatch(r"\d{4}-\d{2}", self.period):
            raise ValueError("Period must be written as YYYY-MM")
        return self
