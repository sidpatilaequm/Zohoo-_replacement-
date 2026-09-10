from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from . import models as M
from .tax import compute, TaxResult
from .fy import fy_label

_RANGES = {
    "invoice": ("inv_prefix", "inv_seq", "inv_fy"),
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


def next_no(ctx, kind, doc_date=None):
    """Generate the next document number."""
    t = ctx.tenant
    pre, seq, fyflag = _RANGES[kind]
    prefix = getattr(t, pre)

    if getattr(t, fyflag):
        from datetime import date
        label = fy_label(t, doc_date or date.today())
        return f"{prefix}{label}/{_fy_seq(ctx, kind, label).next_no:03d}"

    return f"{prefix}{getattr(t, seq):03d}"


def bump(ctx, kind, doc_date=None):
    t = ctx.tenant
    pre, seq, fyflag = _RANGES[kind]

    if getattr(t, fyflag):
        from datetime import date
        label = fy_label(t, doc_date or date.today())
        _fy_seq(ctx, kind, label).next_no += 1
    else:
        setattr(t, seq, getattr(t, seq) + 1)


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
            raise HTTPException(422, f"Line {i}: that material does not exist in this organisation")
        price = li.price if li.price is not None else (m.cost if use_cost else m.price)
        if Decimal(str(price)) <= 0:
            raise HTTPException(422, f"Line {i}: price must be more than zero")
        out.append(
            (
                i,
                m,
                Decimal(str(li.qty)),
                Decimal(str(price)),
                (li.descr2 or "").strip() or None,
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


def invoice_tax(ctx, inv) -> TaxResult:
    lines = [
        (l.line_no, l.material, l.qty, l.price, l.descr2)
        for l in sorted(inv.lines, key=lambda x: x.line_no)
    ]
    return compute(lines, ctx.tenant.state_code, inv.pos_state)


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
    q = select(func.coalesce(func.sum(M.Payment.amount + M.Payment.tds), 0)).where(
        M.Payment.tenant_id == ctx.tenant.id)
    q = q.where(M.Payment.invoice_id == invoice_id) if invoice_id \
        else q.where(M.Payment.vinv_id == vinv_id)
    return Decimal(str(ctx.db.execute(q).scalar_one()))
