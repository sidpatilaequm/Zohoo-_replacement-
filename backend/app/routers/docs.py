from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .. import models as M, schemas as S
from ..deps import Ctx, need
from ..service import (
    next_no,
    bump,
    resolve_reg,
    build_lines,
    tracks_stock,
    invoice_tax,
    po_tax,
    vinv_tax,
    settled,
)
from ..tax import hsn_summary, in_words

router = APIRouter(tags=["documents"])


def tax_json(t):
    f = float
    return {"intra": t.intra, "taxable": f(t.taxable), "cgst": f(t.cgst), "sgst": f(t.sgst),
            "igst": f(t.igst), "tax": f(t.tax), "total": f(t.total), "rounded": f(t.rounded),
            "roundoff": f(t.roundoff), "words": in_words(t.rounded),
            "lines": [{"line_no": L.line_no, "code": L.code, "descr": L.descr, "hsn": L.hsn,
                       "uom": L.uom, "qty": f(L.qty), "price": f(L.price), "amount": f(L.amount),
                       "cgst": f(L.cgst), "sgst": f(L.sgst), "igst": f(L.igst),
                       "rate": f(L.rate)} for L in t.lines],
            "hsn": [{k: (f(v) if isinstance(v, Decimal) else v) for k, v in h.items()}
                    for h in hsn_summary(t)]}


# ============================================================== invoices
@router.get("/invoices")
def list_invoices(ctx: Ctx = Depends(need("saved"))):
    out = []
    for inv in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)
                              .order_by(M.Invoice.doc_date.desc(), M.Invoice.id.desc())).scalars():
        t = invoice_tax(ctx, inv)
        rec = settled(ctx, invoice_id=inv.id)
        out.append({"id": inv.id, "doc_no": inv.doc_no, "doc_type": inv.doc_type,
                    "status": inv.status, "cancelled_on": inv.cancelled_on,
                    "cancel_reason": inv.cancel_reason,
                    "doc_date": inv.doc_date, "due_date": inv.due_date,
                    "customer": inv.customer.name, "customer_id": inv.customer_id,
                    "customer_email": inv.customer.email,
                    "gstin": inv.gstin, "pos_state": inv.pos_state, "po_no": inv.po_no,
                    "po_date": inv.po_date, "taxable": float(t.taxable), "tax": float(t.tax),
                    "total": float(t.rounded), "received": float(rec),
                    "outstanding": (float(t.rounded - rec)
                                    if inv.doc_type == "TAX" and inv.status == "ACTIVE" else None),
                    "intra": t.intra})
    return out


@router.get("/invoices/{iid}")
def get_invoice(iid: int, ctx: Ctx = Depends(need("saved"))):
    inv = ctx.get(M.Invoice, iid)
    if not inv:
        raise HTTPException(404, "No such invoice")
    t, c, o = invoice_tax(ctx, inv), inv.customer, ctx.tenant
    return {"invoice": {"id": inv.id, "doc_no": inv.doc_no, "doc_type": inv.doc_type,
                        "doc_date": inv.doc_date, "due_date": inv.due_date,
                        "po_no": inv.po_no, "po_date": inv.po_date, "gstin": inv.gstin,
                        "pos_state": inv.pos_state, "reverse_chg": inv.reverse_chg},
            "supplier": {"name": o.name, "gstin": o.gstin, "pan": o.pan, "addr": o.addr,
                         "city": o.city, "state": o.state_code, "pin": o.pin,
                         "bank": o.bank, "logo": o.logo},
            "customer": {"name": c.name, "code": c.code, "email": c.email,
                         "party_type": c.party_type,
                         "bill": {"addr": c.bill_addr, "city": c.bill_city,
                                  "state": c.bill_state, "pin": c.bill_pin},
                         "ship": {"addr": c.bill_addr if c.ship_same else c.ship_addr,
                                  "city": c.bill_city if c.ship_same else c.ship_city,
                                  "state": c.bill_state if c.ship_same else c.ship_state,
                                  "pin": c.bill_pin if c.ship_same else c.ship_pin},
                                "ship_same": c.ship_same},
                                "subject": inv.subject,
                                "instructions": inv.instructions,
                                "totals": tax_json(t), "received": float(settled(ctx, invoice_id=inv.id))}


@router.post("/invoices", status_code=201)
def add_invoice(body: S.InvoiceIn, ctx: Ctx = Depends(need("invoice"))):
    c = ctx.get(M.Customer, body.customer_id)
    if not c:
        raise HTTPException(422, "No such customer in this organisation")
    reg = resolve_reg(c, body.gstin)
    if c.party_type == "B2B" and reg is None:
        raise HTTPException(422, "A B2B customer must be billed under a GSTIN")
    if c.party_type == "B2C" and body.gstin:
        raise HTTPException(422, "A B2C invoice cannot carry a recipient GSTIN")
    pos = body.pos_state or (reg.state_code if reg else c.bill_state)
    doc_no = body.doc_no or next_no(ctx, "invoice", body.doc_date)
    if ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)
                      .where(M.Invoice.doc_no == doc_no)).scalar_one_or_none():
        raise HTTPException(409, f"Invoice {doc_no} already exists")
    resolved = build_lines(ctx, body.lines)
    stock = tracks_stock(ctx)

    if stock:
        for i, m, qty, _, _ in resolved:
            if qty > m.stock_qty:
                raise HTTPException(
                    422,
                    f"Line {i}: quantity {qty} exceeds stock of {m.stock_qty}"
                )

    inv = M.Invoice(
        tenant_id=ctx.tenant.id,
        doc_no=doc_no,
        doc_type=body.doc_type,
        doc_date=body.doc_date,
        due_date=body.due_date,
        customer_id=c.id,
        gstin=reg.gstin if reg else None,
        pos_state=pos,
        po_no=body.po_no,
        po_date=body.po_date,
        reverse_chg=body.reverse_chg,
        subject=(body.subject or "").strip() or None,
        instructions=(body.instructions or "").strip() or None,
    )

    ctx.db.add(inv)
    ctx.db.flush()
    for n, m, qty, price, d2 in resolved:
        ctx.db.add(
            M.InvoiceLine(
                invoice_id=inv.id,
                line_no=n,
                material_id=m.id,
                qty=qty,
                price=price,
                descr2=d2,
            )
        )

        if body.doc_type == "TAX" and stock:
            m.stock_qty = m.stock_qty - qty

    if not body.doc_no:
        bump(ctx, "invoice", body.doc_date)
    ctx.db.commit()
    ctx.db.refresh(inv)
    return {"id": inv.id, "doc_no": inv.doc_no, "totals": tax_json(invoice_tax(ctx, inv))}


@router.post("/invoices/{iid}/convert")
def convert(iid: int, doc_no: str | None = None, ctx: Ctx = Depends(need("invoice"))):
    inv = ctx.get(M.Invoice, iid)
    if not inv:
        raise HTTPException(404, "No such invoice")
    if inv.doc_type != "PRO":
        raise HTTPException(409, "Only a proforma can be converted")
    new_no = doc_no or next_no(ctx, "invoice", inv.doc_date)
    if ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)
                      .where(M.Invoice.doc_no == new_no)).scalar_one_or_none():
        raise HTTPException(409, f"Invoice {new_no} already exists")
    inv.converted_from, inv.doc_no, inv.doc_type = inv.doc_no, new_no, "TAX"
    if tracks_stock(ctx):
        for l in inv.lines:
            l.material.stock_qty = l.material.stock_qty - l.qty
    if not doc_no:
        bump(ctx, "invoice", inv.doc_date)
    ctx.db.commit()
    return {"id": inv.id, "doc_no": inv.doc_no, "converted_from": inv.converted_from}


@router.post("/invoices/{iid}/cancel")
def cancel_invoice(iid: int, body: S.CancelIn, ctx: Ctx = Depends(need("invoice"))):
    """Cancel a tax invoice. The document stays on file (a GST document number must
    not be reused and GSTR-1 table 13 reports it as cancelled), but:

    - it drops out of every GST register, GSTR-1 and GSTR-3B, which reverses the
      output tax it carried;
    - stock issued on it comes back;
    - every receipt against it, including any TDS the customer had deducted, is
      reversed by a contra entry dated today that references the original, so
      the TDS receivable and the settlement position both return to nil.
    """
    inv = ctx.get(M.Invoice, iid)
    if not inv:
        raise HTTPException(404, "No such invoice")
    if inv.status == "CANCELLED":
        raise HTTPException(409, f"{inv.doc_no} is already cancelled")
    if inv.doc_type != "TAX":
        raise HTTPException(409, "A proforma is not a tax document; delete it instead")
    today = date.today()
    reversed_entries = []
    for p in ctx.db.execute(ctx.scope(select(M.Payment), M.Payment)
                            .where(M.Payment.invoice_id == inv.id)).scalars():
        if p.reverses_id or Decimal(str(p.amount)) + Decimal(str(p.tds)) == 0:
            continue
        r = M.Payment(tenant_id=ctx.tenant.id, pay_type="REC", pay_date=today,
                      invoice_id=inv.id, amount=-p.amount, tds=-p.tds, mode="Adjustment",
                      bank_ref=p.bank_ref, bank_acct=p.bank_acct, reverses_id=p.id,
                      narration=f"Reversal of RCPT/{p.id:05d} — {inv.doc_no} cancelled")
        ctx.db.add(r)
        reversed_entries.append({"receipt": f"RCPT/{p.id:05d}", "amount": float(p.amount),
                                 "tds": float(p.tds)})
    if tracks_stock(ctx):
        for l in inv.lines:
            l.material.stock_qty = l.material.stock_qty + l.qty
    t = invoice_tax(ctx, inv)
    inv.status, inv.cancelled_on = "CANCELLED", today
    inv.cancelled_by, inv.cancel_reason = ctx.user.name, body.reason
    ctx.db.commit()
    return {"id": inv.id, "doc_no": inv.doc_no, "status": inv.status,
            "gst_reversed": {"taxable": float(t.taxable), "cgst": float(t.cgst),
                             "sgst": float(t.sgst), "igst": float(t.igst)},
            "receipts_reversed": reversed_entries,
            "tds_reversed": float(sum(Decimal(str(r["tds"])) for r in reversed_entries)),
            "stock_restored": (
                [{"code": l.material.code, "qty": float(l.qty)} for l in inv.lines]
                if tracks_stock(ctx) else []
            )}


@router.delete("/invoices/{iid}", status_code=204)
def del_invoice(iid: int, ctx: Ctx = Depends(need("invoice"))):
    inv = ctx.get(M.Invoice, iid)
    if not inv:
        raise HTTPException(404, "No such invoice")
    if settled(ctx, invoice_id=iid) > 0:
        raise HTTPException(409, "That invoice has receipts against it")
    if inv.doc_type == "TAX" and tracks_stock(ctx):
        for l in inv.lines:
            l.material.stock_qty = l.material.stock_qty + l.qty
    ctx.db.delete(inv)
    ctx.db.commit()


# ======================================================= purchase orders
@router.get("/purchase-orders")
def list_pos(ctx: Ctx = Depends(need("po"))):
    out = []
    for po in ctx.db.execute(ctx.scope(select(M.PurchaseOrder), M.PurchaseOrder)
                             .order_by(M.PurchaseOrder.doc_date.desc())).scalars():
        t = po_tax(ctx, po)
        out.append({"id": po.id, "doc_no": po.doc_no, "doc_date": po.doc_date,
                    "req_date": po.req_date, "vendor": po.vendor.name,
                    "vendor_id": po.vendor_id, "vendor_email": po.vendor.email,
                    "gstin": po.gstin, "status": po.status, "bill_addr": po.bill_addr,
                    "ship_addr": po.ship_addr, "taxable": float(t.taxable),
                    "tax": float(t.tax), "total": float(t.rounded), "intra": t.intra,
                    "lines": [{"material_id": l.material_id, "code": l.material.code,
                               "descr": l.material.descr, "qty": float(l.qty),
                               "price": float(l.price), "descr2": l.descr2} for l in po.lines]})
    return out


@router.post("/purchase-orders", status_code=201)
def add_po(body: S.PoIn, ctx: Ctx = Depends(need("po"))):
    v = ctx.get(M.Vendor, body.vendor_id)
    if not v:
        raise HTTPException(422, "No such vendor in this organisation")
    reg = resolve_reg(v, body.gstin)
    doc_no = body.doc_no or next_no(ctx, "po", body.doc_date)
    if ctx.db.execute(ctx.scope(select(M.PurchaseOrder), M.PurchaseOrder)
                      .where(M.PurchaseOrder.doc_no == doc_no)).scalar_one_or_none():
        raise HTTPException(409, f"Purchase order {doc_no} already exists")
    o = ctx.tenant
    bill = body.bill_addr or f"{o.name}\n{o.addr or ''}\n{o.city or ''} {o.pin or ''}\nGSTIN {o.gstin or ''}"
    po = M.PurchaseOrder(tenant_id=o.id, doc_no=doc_no, doc_date=body.doc_date,
                         req_date=body.req_date, vendor_id=v.id,
                         gstin=reg.gstin if reg else None, bill_addr=bill,
                         ship_same=body.ship_same,
                         ship_addr=bill if body.ship_same else body.ship_addr)
    ctx.db.add(po)
    ctx.db.flush()
    for n, m, qty, price, d2 in build_lines(
        ctx, body.lines, use_cost=True
    ):
        ctx.db.add(M.PoLine(po_id=po.id, line_no=n, material_id=m.id, qty=qty, price=price, descr2=d2,))
    if not body.doc_no:
        bump(ctx, "po", body.doc_date)
    ctx.db.commit()
    ctx.db.refresh(po)
    return {"id": po.id, "doc_no": po.doc_no, "totals": tax_json(po_tax(ctx, po))}


# ======================================================= vendor invoices
@router.get("/vendor-invoices")
def list_vinv(ctx: Ctx = Depends(need("vinv"))):
    out = []
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)
                             .order_by(M.VendorInvoice.doc_date.desc())).scalars():
        t = vinv_tax(ctx, vi)
        paid = settled(ctx, vinv_id=vi.id)
        po = ctx.db.get(M.PurchaseOrder, vi.po_id) if vi.po_id else None
        out.append({"id": vi.id, "doc_no": vi.doc_no, "doc_date": vi.doc_date,
                    "due_date": vi.due_date, "vendor": vi.vendor.name,
                    "vendor_id": vi.vendor_id, "po_no": po.doc_no if po else None,
                    "taxable": float(t.taxable), "tax": float(t.tax),
                    "total": float(t.rounded), "paid": float(paid),
                    "outstanding": float(t.rounded - paid), "intra": t.intra})
    return out


@router.post("/vendor-invoices", status_code=201)
def add_vinv(body: S.VendorInvoiceIn, ctx: Ctx = Depends(need("vinv"))):
    po = ctx.get(M.PurchaseOrder, body.po_id) if body.po_id else None
    if body.po_id and not po:
        raise HTTPException(422, "No such purchase order in this organisation")
    vid = po.vendor_id if po else body.vendor_id
    v = ctx.get(M.Vendor, vid)
    if not v:
        raise HTTPException(422, "No such vendor")
    if ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice).where(
            M.VendorInvoice.vendor_id == vid,
            M.VendorInvoice.doc_no == body.doc_no)).scalar_one_or_none():
        raise HTTPException(409, f"{v.name} already has an invoice numbered {body.doc_no}")
    if body.lines:
        resolved = build_lines(ctx, body.lines, use_cost=True)
    elif po:
        resolved = [(l.line_no, l.material, l.qty, l.price, l.descr2)
                    for l in sorted(po.lines, key=lambda x: x.line_no)]
    else:
        raise HTTPException(422, "Give lines, or a purchase order to copy them from")

    vi = M.VendorInvoice(
        tenant_id=ctx.tenant.id,
        doc_no=body.doc_no,
        doc_date=body.doc_date,
        due_date=body.due_date,
        vendor_id=vid,
        gstin=body.gstin or (po.gstin if po else None),
        po_id=body.po_id,
        our_no=next_no(ctx, "vinv", body.doc_date),
    )
    bump(ctx, "vinv", body.doc_date)

    ctx.db.add(vi)
    ctx.db.flush()

    for n, m, qty, price, d2 in resolved:
        ctx.db.add(
            M.VendorInvoiceLine(
                vinv_id=vi.id,
                line_no=n,
                material_id=m.id,
                qty=qty,
                price=price,
                descr2=d2,
            )
        )

        if tracks_stock(ctx):
            m.stock_qty = m.stock_qty + qty

    if po:
        po.status = "INVOICED"

    ctx.db.commit()
    ctx.db.refresh(vi)

    res = {
        "id": vi.id,
        "doc_no": vi.doc_no,
        "totals": tax_json(vinv_tax(ctx, vi)),
    }

    if po:
        pt, vt = po_tax(ctx, po), vinv_tax(ctx, vi)
        res["variance"] = {
            "po_taxable": float(pt.taxable),
            "invoice_taxable": float(vt.taxable),
            "difference": float(vt.taxable - pt.taxable),
        }

    return res


# ============================================================== payments
def _pay_rows(ctx, kind):
    out = []
    for p in ctx.db.execute(ctx.scope(select(M.Payment), M.Payment)
                            .where(M.Payment.pay_type == kind)
                            .order_by(M.Payment.pay_date.desc())).scalars():
        if p.invoice_id:
            d = ctx.db.get(M.Invoice, p.invoice_id)
            party, doc = d.customer.name, d.doc_no
        else:
            d = ctx.db.get(M.VendorInvoice, p.vinv_id)
            party, doc = d.vendor.name, d.doc_no
        out.append({"id": p.id, "pay_date": p.pay_date, "party": party, "doc": doc,
                    "reverses_id": p.reverses_id,
                    "amount": float(p.amount), "tds": float(p.tds), "mode": p.mode,
                    "bank_ref": p.bank_ref, "bank_acct": p.bank_acct,
                    "narration": p.narration})
    return out


@router.get("/receipts")
def receipts(ctx: Ctx = Depends(need("crec"))):
    return _pay_rows(ctx, "REC")


@router.get("/vendor-payments")
def vendor_payments(ctx: Ctx = Depends(need("vpay"))):
    return _pay_rows(ctx, "PAY")


def _make_payment(body: S.PaymentIn, ctx: Ctx):
    if body.pay_type == "REC":
        inv = ctx.get(M.Invoice, body.invoice_id)
        if not inv:
            raise HTTPException(422, "No such invoice")
        if inv.doc_type != "TAX":
            raise HTTPException(422, "A proforma cannot be settled; convert it to a tax invoice first")
        due = invoice_tax(ctx, inv).rounded - settled(ctx, invoice_id=inv.id)
    else:
        vi = ctx.get(M.VendorInvoice, body.vinv_id)
        if not vi:
            raise HTTPException(422, "No such vendor invoice")
        due = vinv_tax(ctx, vi).rounded - settled(ctx, vinv_id=vi.id)
    if body.amount + body.tds > due + Decimal("0.50"):
        raise HTTPException(422,
            f"Amount {body.amount} plus TDS {body.tds} exceeds the outstanding {due}")
    p = M.Payment(tenant_id=ctx.tenant.id, **body.model_dump())
    ctx.db.add(p)
    ctx.db.commit()
    ctx.db.refresh(p)
    return {"id": p.id, "outstanding_after": float(due - body.amount - body.tds)}


@router.post("/receipts", status_code=201)
def add_receipt(body: S.PaymentIn, ctx: Ctx = Depends(need("crec"))):
    body.pay_type = "REC"
    return _make_payment(body, ctx)


@router.post("/vendor-payments", status_code=201)
def add_vendor_payment(body: S.PaymentIn, ctx: Ctx = Depends(need("vpay"))):
    body.pay_type = "PAY"
    return _make_payment(body, ctx)


@router.delete("/payments/{pid}", status_code=204)
def del_payment(pid: int, ctx: Ctx = Depends(need("crec"))):
    p = ctx.get(M.Payment, pid)
    if not p:
        raise HTTPException(404, "No such entry")
    ctx.db.delete(p)
    ctx.db.commit()
