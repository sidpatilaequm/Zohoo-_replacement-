from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from . import models as M
from .tax import compute, TaxResult
from .fy import fy_label

_RANGES = {
    "invoice": ("inv_prefix", "inv_seq", "inv_fy"),
    "proforma": ("pro_prefix", "pro_seq", "pro_fy"),
    "po": ("po_prefix", "po_seq", "po_fy"),
    "vinv": ("vinv_prefix", "vinv_seq", "vinv_fy"),
}


def _fy_seq(ctx, kind, label):
    row = ctx.db.get(M.DocSequence, (ctx.tenant.id, kind, label))
    if not row:
        row = M.DocSequence(
            tenant_id=ctx.tenant.id,
            kind=kind,
            fy=label,
            next_no=1,
        )
        ctx.db.add(row)
        ctx.db.flush()
    return row


_INVOICE_KINDS = {"invoice": "TAX", "proforma": "PRO"}


def doc_fy(ctx, doc_date=None) -> str:
    """The financial year label a document dated `doc_date` belongs to."""
    from datetime import date
    return fy_label(ctx.tenant, doc_date or date.today())


def invoice_no_taken(ctx, doc_type, doc_no, doc_date, exclude_id=None):
    """The invoice already using `doc_no` for this document type in the
    financial year of `doc_date`, or None. Numbers may repeat across years
    and between tax invoices and proformas, never within one year and type."""
    q = ctx.scope(select(M.Invoice), M.Invoice).where(
        M.Invoice.doc_type == doc_type,
        M.Invoice.fy == doc_fy(ctx, doc_date),
        func.lower(M.Invoice.doc_no) == (doc_no or "").strip().lower(),
    )
    if exclude_id:
        q = q.where(M.Invoice.id != exclude_id)
    return ctx.db.execute(q.limit(1)).scalar_one_or_none()


def _formatted(ctx, kind, doc_date, n):
    t = ctx.tenant
    pre, _, fyflag = _RANGES[kind]
    prefix = getattr(t, pre)
    if getattr(t, fyflag):
        return f"{prefix}{doc_fy(ctx, doc_date)}/{n:03d}"
    return f"{prefix}{n:03d}"


def _current(ctx, kind, doc_date):
    t = ctx.tenant
    _, seq, fyflag = _RANGES[kind]
    if getattr(t, fyflag):
        return _fy_seq(ctx, kind, doc_fy(ctx, doc_date)).next_no
    return getattr(t, seq)


def next_no(ctx, kind, doc_date=None):
    """Generate the next document number.

    For invoices and proformas, a number already typed in by hand is
    stepped over, so the automatic series never collides with one."""
    n = _current(ctx, kind, doc_date)
    doc_type = _INVOICE_KINDS.get(kind)
    while doc_type and invoice_no_taken(
            ctx, doc_type, _formatted(ctx, kind, doc_date, n), doc_date):
        n += 1
    return _formatted(ctx, kind, doc_date, n)


def bump(ctx, kind, doc_date=None, used=None):
    """Move the series on past the number just used. When next_no stepped
    over hand-typed numbers to reach `used`, the series follows it there
    instead of going back over them."""
    t = ctx.tenant
    _, seq, fyflag = _RANGES[kind]
    n = start = _current(ctx, kind, doc_date)
    if used is not None:
        n = next((k for k in range(start, start + 1000)
                  if _formatted(ctx, kind, doc_date, k) == used), start)

    if getattr(t, fyflag):
        _fy_seq(ctx, kind, doc_fy(ctx, doc_date)).next_no = n + 1
    else:
        setattr(t, seq, n + 1)


def next_code(ctx, kind):
    """Generate the next automatic customer/vendor/material code."""
    t = ctx.tenant

    pre, seq, model = {
        "customer": ("cust_prefix", "cust_seq", M.Customer),
        "vendor": ("vend_prefix", "vend_seq", M.Vendor),
        "material": ("mat_prefix", "mat_seq", M.Material),
    }[kind]

    n = getattr(t, seq)

    while True:
        code = f"{getattr(t, pre)}{n:03d}"

        if not ctx.db.execute(
            ctx.scope(select(model), model).where(model.code == code)
        ).scalar_one_or_none():
            setattr(t, seq, n + 1)
            return code

        n += 1




def resolve_reg(party, gstin):
    regs = list(party.gstins or [])
    if not regs:
        return None
    if gstin:
        for r in regs:
            if r.gstin == gstin:
                return r
        raise HTTPException(422, f"GSTIN {gstin} is not on {party.name}")
    return next((r for r in regs if r.is_default), regs[0])


def build_lines(ctx, lines_in, use_cost=False):
    out = []
    for i, li in enumerate(lines_in, 1):
        m = ctx.get(M.Material, li.material_id)
        if not m:
            raise HTTPException(
                422,
                f"Line {i}: that material does not exist in this organisation"
            )

        price = li.price if li.price is not None else (
            m.cost if use_cost else m.price
        )

        if Decimal(str(price)) <= 0:
            raise HTTPException(
                422,
                f"Line {i}: price must be more than zero"
            )

        out.append(
            (
                i,
                m,
                Decimal(str(li.qty)),
                Decimal(str(price)),
                (li.descr2 or "").strip() or None,
                bool(
                    getattr(li, "price_inclusive", None)
                    if getattr(li, "price_inclusive", None) is not None
                    else getattr(m, "price_inclusive", False)
                ),
        )
        )
    return out

def tracks_stock(ctx) -> bool:
    """Only trading companies move stock through documents."""
    return ctx.tenant.company_type == "TRADING"

def live_invoices(ctx, doc_type="TAX"):
    """Invoices that count: not cancelled, optionally of one type. Cancelling an
    invoice reverses its GST by dropping it from every register and return."""
    q = ctx.scope(select(M.Invoice), M.Invoice).where(M.Invoice.status != "CANCELLED")
    if doc_type:
        q = q.where(M.Invoice.doc_type == doc_type)
    return q
class _RatedMaterial:
    """The material as this invoice line taxes it.

    A line may select its own permitted GST rates. When present, those
    rates override the material defaults; otherwise the material defaults
    are used.
    """
    __slots__ = ("_m", "sgst_pct", "cgst_pct", "igst_pct")

    def __init__(self, m, sgst, cgst, igst):
        self._m = m
        self.sgst_pct = m.sgst_pct if sgst is None else sgst
        self.cgst_pct = m.cgst_pct if cgst is None else cgst
        self.igst_pct = m.igst_pct if igst is None else igst

    def __getattr__(self, name):
        return getattr(self._m, name)


def _rated(l):
    return _RatedMaterial(
        l.material,
        getattr(l, "sgst_pct", None),
        getattr(l, "cgst_pct", None),
        getattr(l, "igst_pct", None),
    )


def invoice_tax(ctx, inv) -> TaxResult:
    lines = [
        (
            l.line_no,
            _rated(l),
            l.qty,
            l.price,
            l.descr2,
            bool(getattr(l, "price_inclusive", False)),
            (getattr(l, "disc_type", None), getattr(l, "disc_value", 0) or 0),
        )
        for l in sorted(inv.lines, key=lambda x: x.line_no)
    ]
    return compute(lines, ctx.tenant.state_code, inv.pos_state,
                   discount=(getattr(inv, "disc_type", None),
                             getattr(inv, "disc_value", 0) or 0))


def _purchase_tax(ctx, doc) -> TaxResult:
    reg = resolve_reg(doc.vendor, doc.gstin)
    vs = reg.state_code if reg else doc.vendor.state_code
    lines = [
        (l.line_no, l.material, l.qty, l.price, l.descr2)
        for l in sorted(doc.lines, key=lambda x: x.line_no)
    ]
    org_state = ctx.tenant.state_code
    return compute(lines, org_state, org_state if vs == org_state else vs,
                   taxable_supply=reg is not None)


po_tax = _purchase_tax
vinv_tax = _purchase_tax


def settled(ctx, *, invoice_id=None, vinv_id=None) -> Decimal:
    """Money paid plus TDS and GST withheld (v5.0) on an invoice."""
    q = select(func.coalesce(func.sum(M.Payment.amount + M.Payment.tds + M.Payment.gst_tds), 0)).where(
        M.Payment.tenant_id == ctx.tenant.id)
    q = q.where(M.Payment.invoice_id == invoice_id) if invoice_id \
        else q.where(M.Payment.vinv_id == vinv_id)
    return Decimal(str(ctx.db.execute(q).scalar_one()))
