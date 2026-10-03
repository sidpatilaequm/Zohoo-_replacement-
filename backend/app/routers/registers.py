"""Statutory registers and the GSTR-3B reconciliation."""
import csv, io
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from .. import models as M, schemas as S
from ..deps import Ctx, need
from ..service import invoice_tax, vinv_tax, settled, live_invoices, resolve_reg
from ..tax import q2
from ..fy import in_period

router = APIRouter(prefix="/registers", tags=["registers"])
D0 = Decimal("0")
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def gd(d):
    return f"{d.day:02d}-{MON[d.month - 1]}-{d.year}" if d else ""


# ==================================================== invoice register
@router.get("/invoices")
def invoice_register(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """Every customer document, tax and proforma, with its settlement position."""
    out = []
    for inv in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)
                              .order_by(M.Invoice.doc_date, M.Invoice.id)).scalars():
        if not in_period(ctx.tenant, inv.doc_date, period):
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
        if not in_period(ctx.tenant, inv.doc_date, period):
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
        if not in_period(ctx.tenant, vi.doc_date, period):
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
        tds = Decimal(str(p.tds or 0))
        if not in_period(ctx.tenant, p.pay_date, period) or tds <= 0:
            continue
        vi = ctx.db.get(M.VendorInvoice, p.vinv_id)
        if not vi:
            continue
        t = vinv_tax(ctx, vi)
        v = vi.vendor
        gross = Decimal(str(p.amount)) + tds
        rate = (tds / t.taxable * 100) if t.taxable else D0
        out.append({"pay_date": p.pay_date, "vendor": v.name, "vendor_code": v.code,
                    "pan": v.pan, "gstin": vi.gstin,
                    "msme": v.msme_registered, "msme_number": v.msme_number,
                    "vendor_invoice": vi.doc_no, "invoice_date": vi.doc_date,
                    "invoice_taxable": float(t.taxable),
                    "invoice_total": float(t.rounded),
                    "gross": float(gross), "tds": float(tds),
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


# ===================================================== v4.7 — GST and TDS reports
def _states(ctx) -> dict:
    return {c: n for c, n in ctx.db.execute(select(M.State.code, M.State.name)).all()}


def _rate_summary(rows_lines):
    """[(rate, amount, cgst, sgst, igst)] -> one row per GST rate."""
    by = {}
    for rate, amt, c, s_, i in rows_lines:
        k = float(q2(Decimal(str(rate))))
        b = by.setdefault(k, {"rate": k, "taxable": D0, "cgst": D0, "sgst": D0, "igst": D0})
        b["taxable"] += amt; b["cgst"] += c; b["sgst"] += s_; b["igst"] += i
    return [{k: (float(q2(v)) if isinstance(v, Decimal) else v) for k, v in b.items()}
            | {"tax": float(q2(b["cgst"] + b["sgst"] + b["igst"]))} for b in sorted(by.values(), key=lambda x: x["rate"])]


def _month_summary(rows, date_key):
    by = {}
    for r in rows:
        m = str(r[date_key])[:7]
        b = by.setdefault(m, {"month": m, "count": 0, "taxable": D0, "cgst": D0, "sgst": D0, "igst": D0, "total": D0})
        b["count"] += 1
        for k in ("taxable", "cgst", "sgst", "igst", "total"):
            b[k] += Decimal(str(r[k]))
    return [{k: (float(q2(v)) if isinstance(v, Decimal) else v) for k, v in b.items()} for b in sorted(by.values(), key=lambda x: x["month"])]


def _totals(rows, keys=("taxable", "cgst", "sgst", "igst", "tax", "total")):
    return {k: float(q2(sum((Decimal(str(r[k])) for r in rows), D0))) for k in keys}


@router.get("/gst-sales")
def gst_sales(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """GST register for sales — every live tax invoice in the period with the
    customer's GSTIN, B2B or B2C, place of supply and the tax split, plus
    totals by month and by GST rate. Cancelled invoices are listed apart and
    left out of the totals, as GST requires."""
    st = _states(ctx)
    rows, lines = [], []
    for inv in ctx.db.execute(live_invoices(ctx).order_by(M.Invoice.doc_date, M.Invoice.id)).scalars():
        if not in_period(ctx.tenant, inv.doc_date, period):
            continue
        t = invoice_tax(ctx, inv)
        c = inv.customer
        rows.append({"id": inv.id, "doc_no": inv.doc_no, "doc_date": inv.doc_date, "customer": c.name,
                     "customer_code": c.code, "gstin": inv.gstin, "pan": c.pan,
                     "kind": "B2B" if inv.gstin else "B2C",
                     "pos": inv.pos_state, "pos_name": st.get(inv.pos_state, ""),
                     "supply": "Intra-state" if t.intra else "Inter-state",
                     "reverse_charge": inv.reverse_chg == "Y",
                     "taxable": float(t.taxable), "cgst": float(t.cgst), "sgst": float(t.sgst),
                     "igst": float(t.igst), "tax": float(t.tax), "total": float(t.rounded)})
        lines += [(l.rate, l.amount, l.cgst, l.sgst, l.igst) for l in t.lines]
    cancelled = [{"doc_no": inv.doc_no, "doc_date": inv.doc_date, "customer": inv.customer.name,
                  "reason": inv.cancel_reason}
                 for inv in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice).where(
                     M.Invoice.doc_type == "TAX", M.Invoice.status == "CANCELLED")
                     .order_by(M.Invoice.doc_date)).scalars()
                 if in_period(ctx.tenant, inv.doc_date, period)]
    b2b = [r for r in rows if r["kind"] == "B2B"]
    return {"period": period, "rows": rows, "totals": _totals(rows),
            "b2b": _totals(b2b), "b2c": _totals([r for r in rows if r["kind"] == "B2C"]),
            "by_month": _month_summary(rows, "doc_date"), "by_rate": _rate_summary(lines),
            "cancelled": cancelled}


@router.get("/gst-purchases")
def gst_purchases(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """GST register for purchases — every vendor invoice in the period with
    the vendor's GSTIN and the tax split, and whether input tax credit is
    available (a registered vendor charging GST). Totals by month and rate."""
    rows, lines = [], []
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)
                             .order_by(M.VendorInvoice.doc_date, M.VendorInvoice.id)).scalars():
        if not in_period(ctx.tenant, vi.doc_date, period):
            continue
        t = vinv_tax(ctx, vi)
        v = vi.vendor
        reg = resolve_reg(v, vi.gstin)      # the vendor's registration this invoice was under
        rows.append({"id": vi.id, "doc_no": vi.doc_no, "our_no": vi.our_no, "doc_date": vi.doc_date,
                     "vendor": v.name, "vendor_code": v.code, "gstin": reg.gstin if reg else None, "pan": v.pan,
                     "supply": "Intra-state" if t.intra else "Inter-state",
                     "itc": reg is not None and t.tax > 0,
                     "taxable": float(t.taxable), "cgst": float(t.cgst), "sgst": float(t.sgst),
                     "igst": float(t.igst), "tax": float(t.tax), "total": float(t.rounded)})
        lines += [(l.rate, l.amount, l.cgst, l.sgst, l.igst) for l in t.lines]
    itc = [r for r in rows if r["itc"]]
    return {"period": period, "rows": rows, "totals": _totals(rows), "itc": _totals(itc),
            "no_itc_count": len(rows) - len(itc),
            "by_month": _month_summary(rows, "doc_date"), "by_rate": _rate_summary(lines)}


def _tds_due(month: str) -> date:
    """TDS deducted in a month is deposited by the 7th of the next month;
    for March, by 30 April (Rule 30)."""
    y, m = int(month[:4]), int(month[5:7])
    if m == 3:
        return date(y, 4, 30)
    return date(y + (m == 12), 1 if m == 12 else m + 1, 7)


def _quarter(d) -> str:
    """Indian TDS quarters: Q1 Apr–Jun … Q4 Jan–Mar, labelled by FY."""
    y = d.year if d.month >= 4 else d.year - 1
    q = (d.month - 4) // 3 + 1 if d.month >= 4 else 4
    return f"Q{q} {y}-{str(y + 1)[-2:]}"


@router.get("/tds-report")
def tds_report(period: str | None = None, ctx: Ctx = Depends(need("registers"))):
    """TDS both ways.

    Vendors — tax we deducted when paying vendors. It is ours to deposit with
    the government: totals by month and section with the deposit due date,
    and invoices whose TDS has still to be deducted.

    Customers — tax our customers deducted when paying us. It is credit we
    claim against our own tax, once it shows in Form 26AS: by customer and
    quarter."""
    today = date.today()
    vrows, crows = [], []
    for p in ctx.db.execute(ctx.scope(select(M.Payment), M.Payment)
                            .where(M.Payment.tds != 0).order_by(M.Payment.pay_date, M.Payment.id)).scalars():
        if not in_period(ctx.tenant, p.pay_date, period):
            continue
        tds = Decimal(str(p.tds))
        if p.pay_type == "PAY" and p.vinv_id:
            vi = ctx.db.get(M.VendorInvoice, p.vinv_id)
            t = vinv_tax(ctx, vi)
            v = vi.vendor
            vrows.append({"pay_date": p.pay_date, "vendor": v.name, "vendor_code": v.code, "pan": v.pan,
                          "section": v.tds_section or "", "rate": float(v.tds_rate or 0),
                          "invoice": vi.doc_no, "invoice_date": vi.doc_date, "taxable": float(t.taxable),
                          "tds": float(tds), "paid": float(p.amount), "batch_ref": p.batch_ref,
                          "month": str(p.pay_date)[:7]})
        elif p.pay_type == "REC" and p.invoice_id:
            inv = ctx.db.get(M.Invoice, p.invoice_id)
            t = invoice_tax(ctx, inv)
            c = inv.customer
            crows.append({"date": p.pay_date, "customer": c.name, "customer_code": c.code, "pan": c.pan,
                          "invoice": inv.doc_no, "invoice_date": inv.doc_date, "taxable": float(t.taxable),
                          "invoice_total": float(t.rounded), "received": float(p.amount), "tds": float(tds),
                          "quarter": _quarter(p.pay_date), "reversal": bool(p.reverses_id)})
    # vendors: by month (deposit) and by section
    months = {}
    for r in vrows:
        m = months.setdefault(r["month"], {"month": r["month"], "tds": D0, "count": 0})
        m["tds"] += Decimal(str(r["tds"])); m["count"] += 1
    by_month = []
    for m in sorted(months.values(), key=lambda x: x["month"]):
        due = _tds_due(m["month"])
        by_month.append({"month": m["month"], "count": m["count"], "tds": float(q2(m["tds"])),
                         "due_date": due, "status": "Overdue" if due < today else "Due"})
    sections = {}
    for r in vrows:
        k = r["section"] or "Not set"
        sections[k] = sections.get(k, D0) + Decimal(str(r["tds"]))
    # vendor invoices still awaiting their TDS (rate set, not fully deducted, unpaid)
    pending = []
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)
                             .order_by(M.VendorInvoice.doc_date)).scalars():
        rate = Decimal(str(vi.vendor.tds_rate or 0))
        if rate <= 0 or not in_period(ctx.tenant, vi.doc_date, period):
            continue
        t = vinv_tax(ctx, vi)
        expected = (t.taxable * rate / 100).quantize(Decimal("1"))
        done = Decimal(str(ctx.db.execute(select(func.coalesce(func.sum(M.Payment.tds), 0)).where(
            M.Payment.tenant_id == ctx.tenant.id, M.Payment.vinv_id == vi.id)).scalar_one()))
        if expected - done > Decimal("0.5") and t.rounded - settled(ctx, vinv_id=vi.id) > Decimal("0.5"):
            pending.append({"invoice": vi.doc_no, "invoice_date": vi.doc_date, "vendor": vi.vendor.name,
                            "pan": vi.vendor.pan, "section": vi.vendor.tds_section or "",
                            "rate": float(rate), "taxable": float(t.taxable),
                            "expected": float(expected), "deducted": float(done),
                            "to_deduct": float(expected - done)})
    # customers: by customer and quarter
    by_cust = {}
    for r in crows:
        k = (r["customer"], r["quarter"])
        b = by_cust.setdefault(k, {"customer": r["customer"], "pan": r["pan"], "quarter": r["quarter"],
                                   "tds": D0, "received": D0, "count": 0})
        b["tds"] += Decimal(str(r["tds"])); b["received"] += Decimal(str(r["received"])); b["count"] += 1
    cust_summary = [{**b, "tds": float(q2(b["tds"])), "received": float(q2(b["received"]))}
                    for b in sorted(by_cust.values(), key=lambda x: (x["quarter"], x["customer"]))]
    vt = float(q2(sum((Decimal(str(r["tds"])) for r in vrows), D0)))
    ct = float(q2(sum((Decimal(str(r["tds"])) for r in crows), D0)))
    return {"period": period,
            "vendors": {"rows": vrows, "total": vt, "by_month": by_month,
                        "by_section": [{"section": k, "tds": float(q2(v))} for k, v in sorted(sections.items())],
                        "pending": pending, "pending_total": float(q2(sum((Decimal(str(r["to_deduct"])) for r in pending), D0))),
                        "without_pan": sorted({r["vendor"] for r in vrows if not r["pan"]})},
            "customers": {"rows": crows, "total": ct, "by_customer": cust_summary,
                          "without_pan": sorted({r["customer"] for r in crows if not r["pan"]})}}



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
    elif which == "gst-sales":
        d = gst_sales(period, ctx)
        rows = [["Invoice","Date","Customer code","Customer","GSTIN","PAN","B2B/B2C","Place of supply",
                 "Supply","Reverse charge","Taxable","CGST","SGST","IGST","Total tax","Invoice value"]]
        for r in d["rows"]:
            rows.append([r["doc_no"], gd(r["doc_date"]), r["customer_code"], r["customer"], r["gstin"] or "",
                         r["pan"] or "", r["kind"], f'{r["pos"]}-{r["pos_name"]}', r["supply"],
                         "Y" if r["reverse_charge"] else "N", r["taxable"], r["cgst"], r["sgst"], r["igst"],
                         r["tax"], r["total"]])
        t = d["totals"]
        rows.append(["Total", "", "", "", "", "", "", "", "", "", t["taxable"], t["cgst"], t["sgst"], t["igst"], t["tax"], t["total"]])
    elif which == "gst-purchases":
        d = gst_purchases(period, ctx)
        rows = [["Vendor invoice","Our no.","Date","Vendor code","Vendor","GSTIN","PAN","Supply","ITC",
                 "Taxable","CGST","SGST","IGST","Total tax","Invoice value"]]
        for r in d["rows"]:
            rows.append([r["doc_no"], r["our_no"] or "", gd(r["doc_date"]), r["vendor_code"], r["vendor"],
                         r["gstin"] or "", r["pan"] or "", r["supply"], "Yes" if r["itc"] else "No",
                         r["taxable"], r["cgst"], r["sgst"], r["igst"], r["tax"], r["total"]])
        t = d["totals"]
        rows.append(["Total", "", "", "", "", "", "", "", "", t["taxable"], t["cgst"], t["sgst"], t["igst"], t["tax"], t["total"]])
    elif which == "tds-vendors":
        d = tds_report(period, ctx)["vendors"]
        rows = [["Payment date","Vendor code","Vendor","PAN","Section","Rate %","Vendor invoice","Invoice date",
                 "Taxable","TDS deducted","Paid to vendor","Payment ref","Deposit due by"]]
        for r in d["rows"]:
            rows.append([gd(r["pay_date"]), r["vendor_code"], r["vendor"], r["pan"] or "", r["section"], r["rate"],
                         r["invoice"], gd(r["invoice_date"]), r["taxable"], r["tds"], r["paid"],
                         r["batch_ref"] or "", gd(_tds_due(r["month"]))])
        rows.append(["Total", "", "", "", "", "", "", "", "", d["total"], "", "", ""])
    elif which == "tds-customers":
        d = tds_report(period, ctx)["customers"]
        rows = [["Receipt date","Customer code","Customer","PAN","Invoice","Invoice date","Taxable",
                 "Invoice value","Received","TDS deducted by customer","Quarter"]]
        for r in d["rows"]:
            rows.append([gd(r["date"]), r["customer_code"], r["customer"], r["pan"] or "", r["invoice"],
                         gd(r["invoice_date"]), r["taxable"], r["invoice_total"], r["received"], r["tds"], r["quarter"]])
        rows.append(["Total", "", "", "", "", "", "", "", "", d["total"], ""])
    else:
        raise HTTPException(404, "Register must be invoices, gst, tds, gst-sales, gst-purchases, "
                            "tds-vendors or tds-customers")
    return _csv(rows, f"{which}_register_{period or 'all'}.csv")


# ============================================ GSTR-3B upload and compare
def _computed_3b(ctx, period):
    o = {"taxable": D0, "igst": D0, "cgst": D0, "sgst": D0}
    for inv in ctx.db.execute(live_invoices(ctx)).scalars():
        if not in_period(ctx.tenant, inv.doc_date, period):
            continue
        t = invoice_tax(ctx, inv)
        for k in o:
            o[k] += getattr(t, k)
    i = {"igst": D0, "cgst": D0, "sgst": D0}
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)).scalars():
        if not in_period(ctx.tenant, vi.doc_date, period):
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
