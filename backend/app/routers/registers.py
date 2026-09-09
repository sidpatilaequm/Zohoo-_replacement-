"""Statutory registers and the GSTR-3B reconciliation."""
import csv, io
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from .. import models as M, schemas as S
from ..deps import Ctx, need
from ..service import invoice_tax, vinv_tax, settled, live_invoices
from ..tax import q2

router = APIRouter(prefix="/registers", tags=["registers"])
D0 = Decimal("0")
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def gd(d):
    return f"{d.day:02d}-{MON[d.month - 1]}-{d.year}" if d else ""


def _in_period(d, period):
    return not period or str(d)[:7] == period


# ==================================================== invoice register
@router.get("/invoices")
def invoice_register(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """Every customer document, tax and proforma, with its settlement position."""
    out = []
    for inv in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)
                              .order_by(M.Invoice.doc_date, M.Invoice.id)).scalars():
        if not _in_period(inv.doc_date, period):
            continue
        t = invoice_tax(ctx, inv)
        rec = settled(ctx, invoice_id=inv.id)
        c = inv.customer
        out.append({"id": inv.id, "status": inv.status, "cancel_reason": inv.cancel_reason,
                    "doc_type": "Tax invoice" if inv.doc_type == "TAX" else "Proforma",
                    "doc_no": inv.doc_no, "doc_date": inv.doc_date,
                    "customer": c.name, "customer_code": c.code, "gstin": inv.gstin,
                    "pan": c.pan, "msme": c.msme_registered,
                    "place_of_supply": inv.pos_state, "po_no": inv.po_no,
                    "taxable": float(t.taxable), "cgst": float(t.cgst),
                    "sgst": float(t.sgst), "igst": float(t.igst),
                    "total": float(t.rounded),
                    "received": float(rec) if inv.doc_type == "TAX" else None,
                    "outstanding": float(t.rounded - rec) if inv.doc_type == "TAX" else None,
                    "supply": "Intra-state" if t.intra else "Inter-state"})
    return out


# ======================================================== GST register
@router.get("/gst")
def gst_register(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """Outward and inward side by side — what is payable and what is claimable."""
    outward, inward = [], []
    for inv in ctx.db.execute(live_invoices(ctx).order_by(M.Invoice.doc_date)).scalars():
        if not _in_period(inv.doc_date, period):
            continue
        t = invoice_tax(ctx, inv)
        outward.append({"doc_no": inv.doc_no, "doc_date": inv.doc_date,
                        "party": inv.customer.name, "gstin": inv.gstin,
                        "section": "b2b" if inv.gstin else "b2c",
                        "taxable": float(t.taxable), "igst": float(t.igst),
                        "cgst": float(t.cgst), "sgst": float(t.sgst),
                        "total": float(t.rounded)})
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)
                             .order_by(M.VendorInvoice.doc_date)).scalars():
        if not _in_period(vi.doc_date, period):
            continue
        t = vinv_tax(ctx, vi)
        inward.append({"doc_no": vi.doc_no, "doc_date": vi.doc_date,
                       "party": vi.vendor.name, "gstin": vi.gstin,
                       "registered": bool(vi.gstin),
                       "taxable": float(t.taxable), "igst": float(t.igst),
                       "cgst": float(t.cgst), "sgst": float(t.sgst),
                       "total": float(t.rounded)})
    def tot(rows, k):
        return float(q2(sum((Decimal(str(r[k])) for r in rows), D0)))
    o = {k: tot(outward, k) for k in ("taxable", "igst", "cgst", "sgst")}
    i = {k: tot(inward, k) for k in ("taxable", "igst", "cgst", "sgst")}
    net = {k: round(max(0.0, o[k] - i[k]), 2) for k in ("igst", "cgst", "sgst")}
    return {"period": period, "outward": outward, "inward": inward,
            "totals": {"outward": o, "input_credit": i, "net_payable": net},
            "note": ("Input credit is taken from vendor invoices recorded here, not from "
                     "GSTR-2B. Where credit exceeds liability the net is floored at zero "
                     "rather than carried forward.")}


# ======================================================== TDS register
@router.get("/tds")
def tds_register(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """Tax deducted at source when paying vendors, taken from the payment entries."""
    out = []
    for p in ctx.db.execute(ctx.scope(select(M.Payment), M.Payment)
                            .where(M.Payment.pay_type == "PAY")
                            .order_by(M.Payment.pay_date)).scalars():
        if not _in_period(p.pay_date, period) or Decimal(str(p.tds)) <= 0:
            continue
        vi = ctx.db.get(M.VendorInvoice, p.vinv_id)
        if not vi:
            continue
        t = vinv_tax(ctx, vi)
        v = vi.vendor
        gross = Decimal(str(p.amount)) + Decimal(str(p.tds))
        rate = (Decimal(str(p.tds)) / t.taxable * 100) if t.taxable else D0
        out.append({"pay_date": p.pay_date, "vendor": v.name, "vendor_code": v.code,
                    "pan": v.pan, "gstin": vi.gstin,
                    "msme": v.msme_registered, "msme_number": v.msme_number,
                    "vendor_invoice": vi.doc_no, "invoice_date": vi.doc_date,
                    "invoice_taxable": float(t.taxable),
                    "invoice_total": float(t.rounded),
                    "gross": float(gross), "tds": float(p.tds),
                    "paid": float(p.amount), "mode": p.mode, "bank_ref": p.bank_ref,
                    "implied_rate_pct": float(q2(rate))})
    total = float(q2(sum((Decimal(str(r["tds"])) for r in out), D0)))
    missing_pan = [r["vendor"] for r in out if not r["pan"]]
    return {"period": period, "rows": out, "total_tds": total,
            "vendors_without_pan": sorted(set(missing_pan)),
            "note": ("Rate shown is the deduction as a percentage of the taxable value, "
                     "worked back from what was entered. It is not a section rate and does "
                     "not decide the correct rate. A vendor with no PAN on file attracts a "
                     "higher rate under section 206AA.")}


def _csv(rows, filename):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{which}.csv")
def register_csv(which: str, period: str | None = None,
                 ctx: Ctx = Depends(need("registers"))):
    if which == "invoices":
        data = invoice_register(period, ctx)
        head = ["Type","Status","Invoice","Date","Customer code","Customer","GSTIN","PAN","MSME",
                "Place of supply","PO number","Taxable","CGST","SGST","IGST","Total",
                "Received","Outstanding","Supply"]
        rows = [head] + [[r["doc_type"], r["status"].title(), r["doc_no"], gd(r["doc_date"]), r["customer_code"],
            r["customer"], r["gstin"] or "", r["pan"] or "", "Yes" if r["msme"] else "No",
            r["place_of_supply"], r["po_no"] or "", r["taxable"], r["cgst"], r["sgst"],
            r["igst"], r["total"], r["received"] or "", r["outstanding"] or "",
            r["supply"]] for r in data]
    elif which == "gst":
        d = gst_register(period, ctx)
        rows = [["Side","Document","Date","Party","GSTIN","Taxable","IGST","CGST","SGST","Total"]]
        for r in d["outward"]:
            rows.append(["Outward", r["doc_no"], gd(r["doc_date"]), r["party"],
                         r["gstin"] or "", r["taxable"], r["igst"], r["cgst"],
                         r["sgst"], r["total"]])
        for r in d["inward"]:
            rows.append(["Inward", r["doc_no"], gd(r["doc_date"]), r["party"],
                         r["gstin"] or "", r["taxable"], r["igst"], r["cgst"],
                         r["sgst"], r["total"]])
    elif which == "tds":
        d = tds_register(period, ctx)
        rows = [["Payment date","Vendor code","Vendor","PAN","MSME","MSME number",
                 "Vendor invoice","Invoice date","Taxable","Gross","TDS","Paid",
                 "Implied rate %","Mode","Reference"]]
        for r in d["rows"]:
            rows.append([gd(r["pay_date"]), r["vendor_code"], r["vendor"], r["pan"] or "",
                "Yes" if r["msme"] else "No", r["msme_number"] or "", r["vendor_invoice"],
                gd(r["invoice_date"]), r["invoice_taxable"], r["gross"], r["tds"],
                r["paid"], r["implied_rate_pct"], r["mode"], r["bank_ref"] or ""])
    else:
        raise HTTPException(404, "Register must be invoices, gst or tds")
    return _csv(rows, f"{which}_register_{period or 'all'}.csv")


# ============================================ GSTR-3B upload and compare
def _computed_3b(ctx, period):
    o = {"taxable": D0, "igst": D0, "cgst": D0, "sgst": D0}
    for inv in ctx.db.execute(live_invoices(ctx)).scalars():
        if not _in_period(inv.doc_date, period):
            continue
        t = invoice_tax(ctx, inv)
        for k in o:
            o[k] += getattr(t, k)
    i = {"igst": D0, "cgst": D0, "sgst": D0}
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)).scalars():
        if not _in_period(vi.doc_date, period):
            continue
        t = vinv_tax(ctx, vi)
        for k in i:
            i[k] += getattr(t, k)
    return {**{f"out_{k}": q2(v) for k, v in o.items()},
            **{f"itc_{k}": q2(v) for k, v in i.items()}}


@router.post("/gstr3b")
def upload_3b(body: S.Gstr3bIn, ctx: Ctx = Depends(need("gstr"))):
    """Record what was actually filed, so it can be compared with the books."""
    row = ctx.db.execute(ctx.scope(select(M.Gstr3bUpload), M.Gstr3bUpload)
                         .where(M.Gstr3bUpload.period == body.period)).scalar_one_or_none()
    data = body.model_dump(exclude={"period"})
    if row:
        for k, v in data.items():
            setattr(row, k, v)
        row.uploaded_by = ctx.user.name
    else:
        row = M.Gstr3bUpload(tenant_id=ctx.tenant.id, period=body.period,
                             uploaded_by=ctx.user.name, **data)
        ctx.db.add(row)
    ctx.db.commit()
    return compare_3b(body.period, ctx)


@router.post("/gstr3b/upload-csv")
async def upload_3b_csv(period: str = Query(...), file: UploadFile = File(...),
                        ctx: Ctx = Depends(need("gstr"))):
    """Accept the figures as a two-column CSV of field,value."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    fields = {"out_taxable", "out_igst", "out_cgst", "out_sgst",
              "itc_igst", "itc_cgst", "itc_sgst"}
    vals, unknown = {}, []
    for r in csv.reader(io.StringIO(raw)):
        if len(r) < 2:
            continue
        key = r[0].strip().lower().replace(" ", "_").replace("-", "_")
        if key in ("field", "particulars"):
            continue
        if key not in fields:
            unknown.append(r[0].strip())
            continue
        try:
            vals[key] = Decimal(r[1].strip().replace(",", "") or "0")
        except Exception:
            raise HTTPException(422, f"{r[1]} beside {r[0]} is not a number")
    if not vals:
        raise HTTPException(422,
            "No recognised rows. The file needs lines like out_taxable,125000 — "
            f"one per figure from {', '.join(sorted(fields))}.")
    body = S.Gstr3bIn(period=period, **vals)
    res = upload_3b(body, ctx)
    res["ignored_rows"] = unknown
    return res


@router.post("/gstr3b/upload-json")
async def upload_3b_json(period: str = Query(...), file: UploadFile = File(...),
                         ctx: Ctx = Depends(need("gstr"))):
    """Accept the GSTR-3B JSON downloaded from the GST portal (or prepared for it).
    Reads sup_details.osup_det for outward and itc_elg.itc_net (or the itc_avl
    rows) for input credit."""
    import json
    try:
        d = json.loads((await file.read()).decode("utf-8-sig"))
    except Exception:
        raise HTTPException(422, "That file is not valid JSON")
    if isinstance(d, dict) and "data" in d and isinstance(d["data"], dict):
        d = d["data"]
    sup = (d.get("sup_details") or {}).get("osup_det") or {}
    itc = d.get("itc_elg") or {}
    net = itc.get("itc_net")
    if not net:
        net = {"iamt": 0, "camt": 0, "samt": 0}
        for row in itc.get("itc_avl") or []:
            for k in net:
                net[k] += float(row.get(k) or 0)
    if not sup and not itc:
        raise HTTPException(422, "No sup_details or itc_elg found — is this a GSTR-3B JSON?")
    def dec(x):
        return Decimal(str(x or 0))
    body = S.Gstr3bIn(period=period, out_taxable=dec(sup.get("txval")), out_igst=dec(sup.get("iamt")),
                      out_cgst=dec(sup.get("camt")), out_sgst=dec(sup.get("samt")),
                      itc_igst=dec(net.get("iamt")), itc_cgst=dec(net.get("camt")),
                      itc_sgst=dec(net.get("samt")))
    res = upload_3b(body, ctx)
    res["read_from"] = {"outward": bool(sup), "itc": bool(itc),
                        "portal_period": d.get("ret_period"), "portal_gstin": d.get("gstin")}
    return res


@router.get("/gstr3b/compare")
def compare_3b(period: str = Query(...), ctx: Ctx = Depends(need("gstr"))):
    """Filed against books, head by head."""
    filed = ctx.db.execute(ctx.scope(select(M.Gstr3bUpload), M.Gstr3bUpload)
                           .where(M.Gstr3bUpload.period == period)).scalar_one_or_none()
    book = _computed_3b(ctx, period)
    if not filed:
        return {"period": period, "filed": None, "book": {k: float(v) for k, v in book.items()},
                "rows": [], "all_agree": None,
                "note": "Nothing has been uploaded for this period yet."}
    labels = [("out_taxable", "Outward taxable value"), ("out_igst", "Outward IGST"),
              ("out_cgst", "Outward CGST"), ("out_sgst", "Outward SGST"),
              ("itc_igst", "Input credit IGST"), ("itc_cgst", "Input credit CGST"),
              ("itc_sgst", "Input credit SGST")]
    rows = []
    for key, label in labels:
        f = Decimal(str(getattr(filed, key)))
        b = book[key]
        diff = q2(f - b)
        rows.append({"head": label, "field": key, "filed": float(f), "book": float(b),
                     "difference": float(diff), "agrees": abs(diff) <= Decimal("1")})
    return {"period": period, "uploaded_by": filed.uploaded_by,
            "filed": {k: float(getattr(filed, k)) for k, _ in labels},
            "book": {k: float(v) for k, v in book.items()},
            "rows": rows, "all_agree": all(r["agrees"] for r in rows),
            "note": ("Differences within one rupee are treated as rounding. Anything larger "
                     "needs investigating before the return is relied on: the usual causes "
                     "are documents dated outside the period, credit notes, amendments, or "
                     "credit claimed from GSTR-2B that is not recorded here.")}


@router.get("/gstr3b/template.csv")
def template_3b(ctx: Ctx = Depends(need("gstr"))):
    rows = [["field", "value"],
            ["out_taxable", 0], ["out_igst", 0], ["out_cgst", 0], ["out_sgst", 0],
            ["itc_igst", 0], ["itc_cgst", 0], ["itc_sgst", 0]]
    return _csv(rows, "gstr3b_template.csv")
