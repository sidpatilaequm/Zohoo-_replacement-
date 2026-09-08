from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from . import models as M
from .tax import compute, TaxResult


def next_no(ctx, kind):
    t = ctx.tenant
    return f"{t.inv_prefix}{t.inv_seq:03d}" if kind == "invoice" else f"{t.po_prefix}{t.po_seq:03d}"


def bump(ctx, kind):
    if kind == "invoice":
        ctx.tenant.inv_seq += 1
    else:
        ctx.tenant.po_seq += 1


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
        out.append((i, m, Decimal(str(li.qty)), Decimal(str(price))))
    return out


def invoice_tax(ctx, inv) -> TaxResult:
    lines = [(l.line_no, l.material, l.qty, l.price) for l in sorted(inv.lines, key=lambda x: x.line_no)]
    return compute(lines, ctx.tenant.state_code, inv.pos_state)


def _purchase_tax(ctx, doc) -> TaxResult:
    reg = resolve_reg(doc.vendor, doc.gstin)
    vs = reg.state_code if reg else doc.vendor.state_code
    lines = [(l.line_no, l.material, l.qty, l.price) for l in sorted(doc.lines, key=lambda x: x.line_no)]
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
