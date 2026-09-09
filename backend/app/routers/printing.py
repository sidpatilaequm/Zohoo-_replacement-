"""PDF print-outs. Same permission as viewing the document on screen.

`variant` chooses the layout — TRADING (goods) or NONTRADING (services) —
and defaults to the organisation's company type. `disposition=inline`
opens the PDF in the browser instead of downloading it.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from .. import models as M
from ..deps import Ctx, need
from ..service import invoice_tax, po_tax, settled
from ..printing import render_po, render_invoice, render_receipt, VARIANTS
from .docs import tax_json

router = APIRouter(prefix="/print", tags=["print"])


def _variant(ctx, variant):
    v = (variant or ctx.tenant.company_type or "NONTRADING").upper()
    if v not in VARIANTS:
        raise HTTPException(422, "variant must be TRADING or NONTRADING")
    return v


def _org(ctx):
    o = ctx.tenant
    return {"name": o.name, "gstin": o.gstin, "pan": o.pan, "addr": o.addr, "city": o.city,
            "state": o.state_code, "pin": o.pin, "bank": o.bank, "logo": o.logo,
            "company_type": o.company_type}


def _pdf(data: bytes, filename: str, disposition: str):
    disp = "inline" if disposition == "inline" else "attachment"
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{filename}"'})


@router.get("/variants")
def variants(ctx: Ctx = Depends(need("saved"))):
    return {"default": ctx.tenant.company_type,
            "options": [{"key": "TRADING", "label": "Trading — goods (HSN, quantity, delivery)"},
                        {"key": "NONTRADING", "label": "Non-trading — services (SAC, units, period)"}]}


@router.get("/purchase-orders/{pid}.pdf")
def print_po(pid: int, variant: str | None = None, disposition: str = "attachment",
             ctx: Ctx = Depends(need("po"))):
    po = ctx.get(M.PurchaseOrder, pid)
    if not po:
        raise HTTPException(404, "No such purchase order")
    v = po.vendor
    doc = {"doc_no": po.doc_no, "doc_date": po.doc_date, "req_date": po.req_date,
           "status": po.status, "gstin": po.gstin, "bill_addr": po.bill_addr,
           "ship_addr": po.ship_addr,
           "vendor": {"name": v.name, "addr": v.addr, "city": v.city, "pin": v.pin,
                      "pan": v.pan, "email": v.email}}
    pdf = render_po(_org(ctx), doc, tax_json(po_tax(ctx, po)), _variant(ctx, variant))
    return _pdf(pdf, f"{po.doc_no.replace('/', '-')}.pdf", disposition)


@router.get("/invoices/{iid}.pdf")
def print_invoice(iid: int, variant: str | None = None, disposition: str = "attachment",
                  as_type: str | None = Query(None, alias="as"),
                  ctx: Ctx = Depends(need("saved"))):
    """as=PRO prints any invoice in the proforma layout (for approval or advance);
    as=TAX prints it as a tax invoice. Default: the document's own type."""
    inv = ctx.get(M.Invoice, iid)
    if not inv:
        raise HTTPException(404, "No such invoice")
    dt = (as_type or inv.doc_type).upper()
    if dt not in ("TAX", "PRO"):
        raise HTTPException(422, "as must be TAX or PRO")
    c = inv.customer
    doc = {"doc_no": inv.doc_no, "doc_type": dt, "doc_date": inv.doc_date,
           "cancelled": inv.status == "CANCELLED", "cancel_reason": inv.cancel_reason,
           "cancelled_on": inv.cancelled_on,
           "due_date": inv.due_date, "po_no": inv.po_no, "po_date": inv.po_date,
           "gstin": inv.gstin, "pos_state": inv.pos_state, "reverse_chg": inv.reverse_chg,
           "converted_from": inv.converted_from,
           "customer": {"name": c.name, "email": c.email, "pan": c.pan,
                        "party_type": c.party_type, "ship_same": c.ship_same,
                        "bill": {"addr": c.bill_addr, "city": c.bill_city,
                                 "state": c.bill_state, "pin": c.bill_pin},
                        "ship": {"addr": c.bill_addr if c.ship_same else c.ship_addr,
                                 "city": c.bill_city if c.ship_same else c.ship_city,
                                 "state": c.bill_state if c.ship_same else c.ship_state,
                                 "pin": c.bill_pin if c.ship_same else c.ship_pin}}}
    received = settled(ctx, invoice_id=inv.id) if dt == "TAX" and inv.status == "ACTIVE" else 0
    pdf = render_invoice(_org(ctx), doc, tax_json(invoice_tax(ctx, inv)),
                         _variant(ctx, variant), received=received)
    suffix = "-proforma" if dt == "PRO" and inv.doc_type != "PRO" else ""
    return _pdf(pdf, f"{inv.doc_no.replace('/', '-')}{suffix}.pdf", disposition)


@router.get("/receipts/{pid}.pdf")
def print_receipt(pid: int, variant: str | None = None, disposition: str = "attachment",
                  ctx: Ctx = Depends(need("crec"))):
    p = ctx.get(M.Payment, pid)
    if not p or p.pay_type != "REC":
        raise HTTPException(404, "No such receipt")
    if p.reverses_id:
        raise HTTPException(409, "That is a reversal entry, not a receipt")
    inv = ctx.db.get(M.Invoice, p.invoice_id)
    c = inv.customer
    t = invoice_tax(ctx, inv)
    # everything received on this invoice before this entry (by date, then id)
    before = sum((x.amount + x.tds) for x in ctx.db.execute(
        ctx.scope(select(M.Payment), M.Payment).where(
            M.Payment.invoice_id == inv.id, M.Payment.id != p.id,
            ((M.Payment.pay_date < p.pay_date) |
             ((M.Payment.pay_date == p.pay_date) & (M.Payment.id < p.id))))).scalars())
    rc = {"receipt_no": f"RCPT/{p.id:05d}", "pay_date": p.pay_date, "mode": p.mode,
          "bank_ref": p.bank_ref, "bank_acct": p.bank_acct, "narration": p.narration,
          "amount": p.amount + p.tds, "received_before": before,
          "balance_after": t.rounded - before - p.amount - p.tds,
          "customer": {"name": c.name, "addr": c.bill_addr, "city": c.bill_city,
                       "pin": c.bill_pin, "gstin": inv.gstin, "pan": c.pan},
          "invoice": {"doc_no": inv.doc_no, "doc_date": inv.doc_date,
                      "due_date": inv.due_date, "total": t.rounded}}
    pdf = render_receipt(_org(ctx), rc, _variant(ctx, variant))
    return _pdf(pdf, f"RCPT-{p.id:05d}.pdf", disposition)
