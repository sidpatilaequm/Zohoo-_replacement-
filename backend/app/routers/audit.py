"""What the auditor sees: the books reconciled against themselves, automatically.

Nothing here posts, edits or files anything. Every route is a read.

The two reconciliations answer different questions.

GST asks whether three statements of the same month agree: the invoice register,
what GSTR-1 would carry, and what was actually filed in GSTR-3B. Where the filed
figures have not been uploaded the comparison says so rather than quietly
comparing the books against nothing.

TDS asks whether what was deducted matches what the vendor master says should
have been deducted, and flags the cases that carry a legal consequence of their
own: a deduction with no PAN on file, or a rate that does not match the section.
"""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from .. import models as M
from ..deps import Ctx, need
from ..service import invoice_tax, vinv_tax, settled
from ..tax import q2
from .registers import _computed_3b

router = APIRouter(prefix="/audit", tags=["audit"])

TOL = Decimal("1.00")          # a rupee, which is rounding rather than a difference


def _f(x):
    return float(Decimal(str(x or 0)))


def _in_period(d, period):
    return period is None or str(d)[:7] == period


# ============================================================== GST
def _gst_reconciliation(ctx, period):
    """Invoice register against GSTR-1 against what was filed in GSTR-3B."""
    invs = [i for i in ctx.db.execute(
        ctx.scope(select(M.Invoice), M.Invoice)).scalars()
        if _in_period(i.doc_date, period)]

    books = {"taxable": Decimal("0"), "igst": Decimal("0"),
             "cgst": Decimal("0"), "sgst": Decimal("0")}
    excluded = {"proforma": 0, "cancelled": 0}
    for i in invs:
        if i.status == "CANCELLED":
            excluded["cancelled"] += 1
            continue
        if i.doc_type != "TAX":
            excluded["proforma"] += 1
            continue
        t = invoice_tax(ctx, i)
        books["taxable"] += t.taxable
        books["igst"] += t.igst
        books["cgst"] += t.cgst
        books["sgst"] += t.sgst

    computed = _computed_3b(ctx, period) if period else None

    filed = {}
    if period:
        for row in ctx.db.execute(ctx.scope(select(M.Gstr3bUpload), M.Gstr3bUpload)
                                  .where(M.Gstr3bUpload.period == period)).scalars():
            filed = {"taxable": row.out_taxable, "igst": row.out_igst,
                     "cgst": row.out_cgst, "sgst": row.out_sgst,
                     "itc_igst": row.itc_igst, "itc_cgst": row.itc_cgst,
                     "itc_sgst": row.itc_sgst, "uploaded_by": row.uploaded_by}
            break

    rows = []
    for head, label in [("taxable", "Taxable value"), ("igst", "IGST"),
                        ("cgst", "CGST"), ("sgst", "SGST")]:
        b = Decimal(str(books[head]))
        g1 = Decimal(str(computed["out_" + head])) if computed else None
        f3 = Decimal(str(filed.get(head))) if filed else None
        row = {"head": label, "register": _f(b),
               "gstr1": _f(g1) if g1 is not None else None,
               "gstr3b_filed": _f(f3) if f3 is not None else None}
        row["register_vs_gstr1"] = _f(b - g1) if g1 is not None else None
        row["gstr1_vs_filed"] = _f(g1 - f3) if (g1 is not None and f3 is not None) else None
        row["agrees"] = (
            (g1 is None or abs(b - g1) <= TOL) and
            (f3 is None or g1 is None or abs(g1 - f3) <= TOL))
        rows.append(row)

    issues = []
    for r in rows:
        if r["register_vs_gstr1"] is not None and abs(r["register_vs_gstr1"]) > 1:
            issues.append(f"{r['head']}: the register and GSTR-1 differ by "
                          f"{r['register_vs_gstr1']:,.2f}")
        if r["gstr1_vs_filed"] is not None and abs(r["gstr1_vs_filed"]) > 1:
            issues.append(f"{r['head']}: GSTR-1 and the filed GSTR-3B differ by "
                          f"{r['gstr1_vs_filed']:,.2f}")
    if period and not filed:
        issues.append("No GSTR-3B has been uploaded for this period, so the books "
                      "have nothing to be compared against.")

    return {"period": period, "rows": rows, "excluded": excluded,
            "filed_uploaded_by": filed.get("uploaded_by") if filed else None,
            "issues": issues, "clean": not issues}


# ============================================================== TDS
def _tds_reconciliation(ctx, period):
    """Deducted against what the vendor master says should have been deducted."""
    pays = [p for p in ctx.db.execute(
        ctx.scope(select(M.Payment), M.Payment)
        .where(M.Payment.pay_type == "PAY")).scalars()
        if _in_period(p.pay_date, period)]

    rows, issues = [], []
    total_deducted = Decimal("0")
    total_expected = Decimal("0")
    for p in pays:
        vi = ctx.db.get(M.VendorInvoice, p.vinv_id) if p.vinv_id else None
        if not vi:
            continue
        v = vi.vendor
        t = vinv_tax(ctx, vi)
        base = Decimal(str(t.taxable))          # TDS is on the value before tax
        rate = Decimal(str(v.tds_rate or 0))
        expected = q2(base * rate / 100) if rate else Decimal("0")
        actual = Decimal(str(p.tds or 0))
        diff = actual - expected
        total_deducted += actual
        total_expected += expected

        flags = []
        if actual > 0 and not v.pan:
            flags.append("No PAN on file. Section 206AA requires a higher rate "
                         "where the deductee has not furnished a PAN.")
        if actual > 0 and not v.tds_section:
            flags.append("No section recorded against the vendor, so the deduction "
                         "cannot be reported.")
        if rate and abs(diff) > TOL:
            flags.append(f"Deducted {actual:,.2f} against {expected:,.2f} expected at "
                         f"{rate}% under {v.tds_section or 'no section'}.")
        if not rate and actual > 0:
            flags.append("Tax was deducted although the vendor master carries no rate.")
        if rate and actual == 0:
            flags.append(f"Nothing deducted although the vendor master carries "
                         f"{rate}% under {v.tds_section or 'no section'}.")

        rows.append({
            "pay_date": p.pay_date, "vendor": v.name, "vendor_code": v.code,
            "pan": v.pan, "section": v.tds_section,
            "master_rate_pct": _f(rate), "vendor_invoice": vi.doc_no,
            "invoice_date": vi.doc_date, "taxable": _f(base),
            "expected_tds": _f(expected), "actual_tds": _f(actual),
            "difference": _f(diff),
            "implied_rate_pct": _f(q2(actual / base * 100)) if base else 0.0,
            "paid": _f(p.amount), "bank_ref": p.bank_ref,
            "flags": flags, "agrees": not flags})
        issues.extend(f"{v.name} · {vi.doc_no}: {m}" for m in flags)

    return {"period": period, "rows": rows,
            "total_deducted": _f(total_deducted),
            "total_expected": _f(total_expected),
            "difference": _f(total_deducted - total_expected),
            "vendors_without_pan": sorted({r["vendor"] for r in rows
                                           if r["actual_tds"] and not r["pan"]}),
            "issues": issues, "clean": not issues}


# ============================================================ routes
@router.get("/reconcile")
def reconcile(period: str | None = Query(None, description="YYYY-MM, or all periods"),
              ctx: Ctx = Depends(need("audit"))):
    """Run both reconciliations and say plainly whether anything needs looking at."""
    gst = _gst_reconciliation(ctx, period)
    tds = _tds_reconciliation(ctx, period)
    issues = len(gst["issues"]) + len(tds["issues"])
    return {"period": period, "gst": gst, "tds": tds,
            "issue_count": issues,
            "clean": issues == 0,
            "note": ("Nothing to look at. Every head agrees within a rupee and every "
                     "deduction matches the vendor master."
                     if issues == 0 else
                     f"{issues} item{'' if issues == 1 else 's'} need looking at. "
                     "These are differences in the records held here, not a filing.")}


@router.get("/transactions")
def transactions(period: str | None = None, ctx: Ctx = Depends(need("audit"))):
    """Every document in one list, so the auditor need not walk five screens."""
    out = []
    for i in ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)).scalars():
        if not _in_period(i.doc_date, period):
            continue
        t = invoice_tax(ctx, i)
        out.append({"kind": "Customer invoice", "doc_no": i.doc_no,
                    "doc_date": i.doc_date, "party": i.customer.name,
                    "gstin": i.gstin, "status": i.status,
                    "doc_type": "Proforma" if i.doc_type == "PRO" else "Tax invoice",
                    "taxable": _f(t.taxable), "tax": _f(t.tax), "total": _f(t.rounded),
                    "settled": _f(settled(ctx, invoice_id=i.id))})
    for vi in ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)).scalars():
        if not _in_period(vi.doc_date, period):
            continue
        t = vinv_tax(ctx, vi)
        out.append({"kind": "Vendor invoice", "doc_no": vi.doc_no,
                    "doc_date": vi.doc_date, "party": vi.vendor.name,
                    "gstin": vi.gstin, "status": "ACTIVE", "doc_type": "Vendor invoice",
                    "taxable": _f(t.taxable), "tax": _f(t.tax), "total": _f(t.rounded),
                    "settled": _f(settled(ctx, vinv_id=vi.id))})
    for p in ctx.db.execute(ctx.scope(select(M.Payment), M.Payment)).scalars():
        if not _in_period(p.pay_date, period):
            continue
        if p.invoice_id:
            d = ctx.db.get(M.Invoice, p.invoice_id)
            party, ref = (d.customer.name, d.doc_no) if d else ("", "")
            kind = "Receipt"
        else:
            d = ctx.db.get(M.VendorInvoice, p.vinv_id)
            party, ref = (d.vendor.name, d.doc_no) if d else ("", "")
            kind = "Payment"
        out.append({"kind": kind, "doc_no": ref, "doc_date": p.pay_date,
                    "party": party, "gstin": None, "status": "ACTIVE",
                    "doc_type": f"{kind} · {p.mode}",
                    "taxable": None, "tax": _f(p.tds), "total": _f(p.amount),
                    "settled": None})
    out.sort(key=lambda r: (str(r["doc_date"]), r["kind"]), reverse=True)
    return out
