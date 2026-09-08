"""GSTR-1 sections, GSTR-3B summary, the reconciliation between them, and reports."""
import csv, io
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from .. import models as M
from ..deps import Ctx, need
from ..service import invoice_tax, vinv_tax, settled
from ..tax import q2

router = APIRouter(prefix="/returns", tags=["returns"])
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def gd(d):
    return f"{d.day:02d}-{MON[d.month - 1]}-{d.year}" if d else ""


def _pos(ctx, code):
    s = ctx.db.get(M.State, code)
    return f"{code}-{s.name}" if s else code


def _tax_invoices(ctx, period):
    q = ctx.scope(select(M.Invoice), M.Invoice).where(
        M.Invoice.doc_type == "TAX").order_by(M.Invoice.doc_date)
    return [i for i in ctx.db.execute(q).scalars() if str(i.doc_date)[:7] == period]


@router.get("/periods")
def periods(ctx: Ctx = Depends(need("gstr"))):
    p = {str(i.doc_date)[:7] for i in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)).scalars()}
    p |= {str(v.doc_date)[:7] for v in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)).scalars()}
    return sorted(p, reverse=True)


@router.get("/gstr1")
def gstr1(period: str = Query(..., description="YYYY-MM"), ctx: Ctx = Depends(need("gstr"))):
    """The return as it would be filed, split into its sections."""
    sec = {"b2b": [], "b2cl": [], "b2cs": []}
    tot = {"taxable": Decimal(0), "cgst": Decimal(0), "sgst": Decimal(0), "igst": Decimal(0)}
    for inv in _tax_invoices(ctx, period):
        t = invoice_tax(ctx, inv)
        for k in tot:
            tot[k] += getattr(t, k)
        row = {"doc_no": inv.doc_no, "doc_date": gd(inv.doc_date),
               "recipient": inv.customer.name, "gstin": inv.gstin,
               "pos": _pos(ctx, inv.pos_state), "invoice_value": float(t.rounded),
               "taxable": float(t.taxable), "igst": float(t.igst),
               "cgst": float(t.cgst), "sgst": float(t.sgst),
               "reverse_chg": inv.reverse_chg}
        if inv.gstin:
            sec["b2b"].append(row)
        elif not t.intra and t.rounded > 250000:
            sec["b2cl"].append(row)
        else:
            sec["b2cs"].append(row)
    proforma = len([i for i in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice).where(M.Invoice.doc_type == "PRO")).scalars()
        if str(i.doc_date)[:7] == period])
    return {"period": period, "sections": sec,
            "totals": {k: float(q2(v)) for k, v in tot.items()},
            "proforma_excluded": proforma}


@router.get("/gstr3b")
def gstr3b(period: str = Query(...), ctx: Ctx = Depends(need("gstr"))):
    out = {"taxable": Decimal(0), "cgst": Decimal(0), "sgst": Decimal(0), "igst": Decimal(0)}
    n_out = 0
    for inv in _tax_invoices(ctx, period):
        t = invoice_tax(ctx, inv)
        n_out += 1
        for k in out:
            out[k] += getattr(t, k)
    inp = {"taxable": Decimal(0), "cgst": Decimal(0), "sgst": Decimal(0), "igst": Decimal(0)}
    n_in = 0
    vinvs = [v for v in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)).scalars()
             if str(v.doc_date)[:7] == period]
    for vi in vinvs:
        t = vinv_tax(ctx, vi)
        n_in += 1
        for k in inp:
            inp[k] += getattr(t, k)
    net = {k: max(Decimal(0), out[k] - inp[k]) for k in ("cgst", "sgst", "igst")}
    return {"period": period,
            "outward": {**{k: float(q2(v)) for k, v in out.items()}, "documents": n_out},
            "itc": {**{k: float(q2(v)) for k, v in inp.items()}, "documents": n_in,
                    "source": "vendor invoices"},
            "net_payable": {k: float(q2(v)) for k, v in net.items()},
            "caveat": ("Input credit is taken from vendor invoices recorded here, not from "
                       "GSTR-2B. Blocked credits under section 17(5), reverse charge and "
                       "credit reversals are not handled.")}


@router.get("/reconciliation")
def reconciliation(period: str = Query(...), ctx: Ctx = Depends(need("gstr"))):
    g1 = gstr1(period, ctx)
    g3 = gstr3b(period, ctx)
    rows = []
    for head in ("taxable", "igst", "cgst", "sgst"):
        a, b = g1["totals"][head], g3["outward"][head]
        rows.append({"head": head, "gstr1": a, "gstr3b": b,
                     "difference": round(a - b, 2), "agrees": abs(a - b) < 0.5})
    return {"period": period, "rows": rows, "all_agree": all(r["agrees"] for r in rows),
            "note": ("Both are built from the same set of tax invoices, so a difference "
                     "here indicates a data problem rather than a reconciling item. Credit "
                     "and debit notes, advances, exports and amendments are not covered.")}


def _csv(rows, filename):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/gstr1/{section}.csv")
def gstr1_csv(section: str, period: str = Query(...), ctx: Ctx = Depends(need("gstr"))):
    """Section CSVs in the layout the GST Returns Offline Tool imports."""
    g = gstr1(period, ctx)
    if section == "b2b":
        rows = [["GSTIN/UIN of Recipient", "Receiver Name", "Invoice Number", "Invoice date",
                 "Invoice Value", "Place Of Supply", "Reverse Charge",
                 "Applicable % of Tax Rate", "Invoice Type", "E-Commerce GSTIN",
                 "Rate", "Taxable Value", "Cess Amount"]]
        for r in g["sections"]["b2b"]:
            rate = 18 if r["taxable"] else 0
            rows.append([r["gstin"], r["recipient"], r["doc_no"], r["doc_date"],
                         r["invoice_value"], r["pos"], r["reverse_chg"], "", "Regular B2B",
                         "", rate, r["taxable"], ""])
    elif section == "b2cs":
        rows = [["Type", "Place Of Supply", "Rate", "Applicable % of Tax Rate",
                 "Taxable Value", "Cess Amount", "E-Commerce GSTIN"]]
        agg = {}
        for r in g["sections"]["b2cs"]:
            agg[r["pos"]] = agg.get(r["pos"], 0) + r["taxable"]
        for pos, val in agg.items():
            rows.append(["OE", pos, 18, "", round(val, 2), "", ""])
    elif section == "hsn":
        rows = [["HSN", "Description", "UQC", "Total Quantity", "Total Value", "Rate",
                 "Taxable Value", "Integrated Tax Amount", "Central Tax Amount",
                 "State/UT Tax Amount", "Cess Amount"]]
        agg = {}
        for inv in _tax_invoices(ctx, period):
            t = invoice_tax(ctx, inv)
            for L in t.lines:
                k = (L.hsn, str(L.rate), L.uom)
                a = agg.setdefault(k, {"d": L.descr, "q": Decimal(0), "v": Decimal(0),
                                       "t": Decimal(0), "i": Decimal(0), "c": Decimal(0),
                                       "s": Decimal(0)})
                a["q"] += L.qty
                a["t"] += L.amount
                a["v"] += L.amount + L.cgst + L.sgst + L.igst
                a["i"] += L.igst
                a["c"] += L.cgst
                a["s"] += L.sgst
        for (hsn, rate, uom), a in agg.items():
            rows.append([hsn, a["d"], uom, float(a["q"]), float(q2(a["v"])), rate,
                         float(q2(a["t"])), float(q2(a["i"])), float(q2(a["c"])),
                         float(q2(a["s"])), ""])
    else:
        nos = sorted(r["doc_no"] for s in g["sections"].values() for r in s)
        rows = [["Nature of Document", "Sr. No. From", "Sr. No. To", "Total Number", "Cancelled"],
                ["Invoices for outward supply", nos[0] if nos else "",
                 nos[-1] if nos else "", len(nos), 0]]
    return _csv(rows, f"{section}_{period}.csv")


# ------------------------------------------------------------- reports
@router.get("/reports/receivables")
def receivables(ctx: Ctx = Depends(need("reports"))):
    out = []
    for inv in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice).where(M.Invoice.doc_type == "TAX")).scalars():
        t = invoice_tax(ctx, inv)
        rec = settled(ctx, invoice_id=inv.id)
        bal = t.rounded - rec
        if bal <= Decimal("0.5"):
            continue
        out.append({"customer": inv.customer.name, "doc_no": inv.doc_no,
                    "doc_date": inv.doc_date, "due_date": inv.due_date,
                    "total": float(t.rounded), "received": float(rec),
                    "outstanding": float(bal)})
    return sorted(out, key=lambda r: r["doc_date"])


@router.get("/reports/payables")
def payables(ctx: Ctx = Depends(need("gstr"))):
    out = []
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)).scalars():
        t = vinv_tax(ctx, vi)
        paid = settled(ctx, vinv_id=vi.id)
        bal = t.rounded - paid
        if bal <= Decimal("0.5"):
            continue
        out.append({"vendor": vi.vendor.name, "doc_no": vi.doc_no, "doc_date": vi.doc_date,
                    "due_date": vi.due_date, "total": float(t.rounded),
                    "paid": float(paid), "outstanding": float(bal)})
    return sorted(out, key=lambda r: r["doc_date"])


@router.get("/reports/margin")
def margin(ctx: Ctx = Depends(need("gstr"))):
    out = []
    for m in ctx.db.execute(ctx.scope(select(M.Material), M.Material).order_by(M.Material.code)).scalars():
        sq = sv = bq = bv = Decimal(0)
        for l in ctx.db.execute(select(M.InvoiceLine).where(M.InvoiceLine.material_id == m.id)).scalars():
            if l.invoice.doc_type == "TAX":
                sq += l.qty
                sv += l.qty * l.price
        for l in ctx.db.execute(select(M.VendorInvoiceLine).where(M.VendorInvoiceLine.material_id == m.id)).scalars():
            bq += l.qty
            bv += l.qty * l.price
        if not sq and not bq:
            continue
        out.append({"code": m.code, "descr": m.descr, "sold_qty": float(sq),
                    "sales_value": float(q2(sv)), "bought_qty": float(bq),
                    "purchase_value": float(q2(bv)), "margin": float(q2(sv - bv)),
                    "margin_pct": float(q2((sv - bv) / sv * 100)) if sv else None})
    return out
