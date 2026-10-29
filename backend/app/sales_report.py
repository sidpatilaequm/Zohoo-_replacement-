"""Sales reports: sales by customer, by material and by employee (the user who
created the invoice), over a preset or custom date range.

What counts as a sale: a TAX invoice that is not cancelled, dated inside the
range. Proformas are not sales, and a cancelled invoice reverses its sale, as
in every other register.

Ranges follow the organisation's financial year (Company profile, default
1 April). "This quarter" is the financial quarter: for an April year, Q1 is
April–June. "This year" is the financial year (FY 2026-27). Weeks run Monday to
Sunday.

Amounts
- Customer and employee rows use whole invoices: taxable value, GST, and the
  rounded invoice total, so they agree with the Invoice Register.
- Material rows use invoice lines: taxable value, GST and line value (taxable +
  GST). Invoice round-off belongs to no line, so the material total can differ
  from the invoice totals by the round-off, which is reported separately.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from . import models as M
from .fy import fy_bounds, fy_label
from .service import invoice_tax, live_invoices
from .tax import q2

GROUPS = ("customer", "material", "employee")


PRESETS = [
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("this_week", "This week"),
    ("this_month", "This month"),
    ("this_quarter", "This quarter"),
    ("this_year", "This year"),
    ("prev_month", "Previous month"),
    ("prev_quarter", "Previous quarter"),
    ("prev_year", "Previous year"),
    ("custom", "Custom dates"),
]

PRESET_KEYS = {k for k, _ in PRESETS}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ZERO = Decimal("0")


# ------------------------------------------------------------ date ranges
def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def _fy_of(tenant, d: date) -> tuple[date, date, str]:
    label = fy_label(tenant, d)
    a, b = fy_bounds(tenant, label)
    return a, b, label


def _quarter_of(tenant, d: date) -> tuple[date, date, int, str]:
    fa, _, label = _fy_of(tenant, d)
    q = 0
    while add_months(fa, 3 * (q + 1)) <= d:
        q += 1
    a = add_months(fa, 3 * q)
    b = add_months(fa, 3 * (q + 1)) - timedelta(days=1)
    return a, b, q + 1, label


def _fy_text(label: str) -> str:
    return f"FY {label}"


def resolve_range(tenant, key: str, today: date,
                  start: date | None = None, end: date | None = None) -> dict:
    """Turn a preset (or custom dates) into {key, label, start, end}."""
    if key not in PRESET_KEYS:
        raise HTTPException(422, f"Unknown date range {key!r}")
    if key == "custom":
        if not start or not end:
            raise HTTPException(422, "Choose both a start date and an end date")
        if start > end:
            raise HTTPException(422, "The start date is after the end date")
        return {"key": key, "label": "Custom dates", "start": start, "end": end}


    if key == "today":
        a = b = today
        label = "Today"
    elif key == "yesterday":
        a = b = today - timedelta(days=1)
        label = "Yesterday"
    elif key == "this_week":

        a = today - timedelta(days=today.weekday())
        b = a + timedelta(days=6)
        label = "This week"
    elif key in ("this_month", "prev_month"):
        first = today.replace(day=1)
        if key == "prev_month":
            first = add_months(first, -1)
        a, b = first, first.replace(day=monthrange(first.year, first.month)[1])
        label = f"{'This' if key == 'this_month' else 'Previous'} month ({MON[a.month - 1]} {a.year})"
    elif key in ("this_quarter", "prev_quarter"):
        a, b, q, fy = _quarter_of(tenant, today)
        if key == "prev_quarter":
            a, b, q, fy = _quarter_of(tenant, a - timedelta(days=1))
        label = (f"{'This' if key == 'this_quarter' else 'Previous'} quarter "
                 f"(Q{q} {_fy_text(fy)}, {MON[a.month - 1]}–{MON[b.month - 1]})")
    else:  # this_year / prev_year
        a, b, fy = _fy_of(tenant, today)
        if key == "prev_year":
            a, b, fy = _fy_of(tenant, a - timedelta(days=1))
        label = f"{'This' if key == 'this_year' else 'Previous'} year ({_fy_text(fy)})"
    return {"key": key, "label": label, "start": a, "end": b}


def all_ranges(tenant, today: date) -> list[dict]:
    out = []
    for k, name in PRESETS:
        if k == "custom":
            out.append({"key": k, "name": name, "label": name, "start": None, "end": None})
        else:
            r = resolve_range(tenant, k, today)
            out.append({"key": k, "name": name, **r})
    return out


# ------------------------------------------------------------ aggregation
def _f(x: Decimal) -> float:
    return float(q2(x))


def _blank(**extra) -> dict:
    return {"invoices": set(), "taxable": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO,
            "total": ZERO, "docs": {}, **extra}


def _employee_index(ctx) -> dict:
    rows = ctx.db.execute(ctx.scope(select(M.Employee), M.Employee)).scalars()
    return {(e.email or "").strip().lower(): e for e in rows}


def sales_report(ctx, group: str, start: date, end: date) -> dict:
    if group not in GROUPS:
        raise HTTPException(422, f"Report must be one of: {', '.join(GROUPS)}")
    q = (live_invoices(ctx)
         .where(M.Invoice.doc_date >= start, M.Invoice.doc_date <= end)
         .order_by(M.Invoice.doc_date, M.Invoice.id))
    invoices = list(ctx.db.execute(q).scalars())
    employees = _employee_index(ctx) if group == "employee" else {}

    rows: dict = {}
    grand = _blank(roundoff=ZERO)
    for inv in invoices:
        t = invoice_tax(ctx, inv)
        grand["invoices"].add(inv.id)
        grand["taxable"] += t.taxable
        grand["cgst"] += t.cgst
        grand["sgst"] += t.sgst
        grand["igst"] += t.igst
        grand["total"] += t.rounded
        grand["roundoff"] += t.roundoff
        doc_base = {"id": inv.id, "doc_no": inv.doc_no, "doc_date": inv.doc_date,
                    "customer": inv.customer.name}

        if group == "material":
            mat_by_line = {l.line_no: l.material for l in inv.lines}
            for L in t.lines:
                m = mat_by_line.get(L.line_no)
                key = f"m{m.id}" if m else f"c{L.code}"
                r = rows.setdefault(key, _blank(
                    code=m.code if m else L.code, descr=m.descr if m else L.descr,
                    uom=L.uom, hsn=L.hsn, qty=ZERO))
                line_total = L.amount + L.cgst + L.sgst + L.igst
                r["qty"] += L.qty
                r["taxable"] += L.amount
                r["cgst"] += L.cgst
                r["sgst"] += L.sgst
                r["igst"] += L.igst
                r["total"] += line_total
                r["invoices"].add(inv.id)
                d = r["docs"].setdefault(inv.id, {**doc_base, "qty": ZERO, "taxable": ZERO, "total": ZERO})
                d["qty"] += L.qty
                d["taxable"] += L.amount
                d["total"] += line_total
            continue

        if group == "customer":
            c = inv.customer
            key = f"c{c.id}"
            r = rows.setdefault(key, _blank(code=c.code, name=c.name,
                                            party_type=getattr(c, "party_type", None)))
        else:
            u = inv.created_by
            if u is None:
                key = "none"
                r = rows.setdefault(key, _blank(user_id=None, name="Not recorded",
                                                email=None, emp_code=None, emp_name=None,
                                                note="Created before v4.4, when the creator was not stored"))
            else:
                e = employees.get((u.email or "").strip().lower())
                key = f"u{u.id}"
                r = rows.setdefault(key, _blank(
                    user_id=u.id, name=u.name, email=u.email,
                    emp_code=e.emp_code if e else None,
                    emp_name=f"{e.first_name} {e.last_name}".strip() if e else None, note=None))
        r["taxable"] += t.taxable
        r["cgst"] += t.cgst
        r["sgst"] += t.sgst
        r["igst"] += t.igst
        r["total"] += t.rounded
        r["invoices"].add(inv.id)
        r["docs"][inv.id] = {**doc_base, "taxable": t.taxable, "total": t.rounded}

    base_total = sum((r["total"] for r in rows.values()), ZERO)
    out = []
    for r in sorted(rows.values(), key=lambda x: (-x["total"], x.get("code") or x.get("name") or "")):
        row = {k: v for k, v in r.items() if k not in ("invoices", "docs")}
        for k in ("taxable", "cgst", "sgst", "igst", "total"):
            row[k] = _f(r[k])
        row["tax"] = _f(r["cgst"] + r["sgst"] + r["igst"])
        row["invoice_count"] = len(r["invoices"])
        row["share_pct"] = _f(r["total"] / base_total * 100) if base_total else 0.0
        if group == "material":
            row["qty"] = float(r["qty"])
            row["avg_price"] = _f(r["taxable"] / r["qty"]) if r["qty"] else None
        row["docs"] = [{**d, **{k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}}
                       for d in sorted(r["docs"].values(), key=lambda d: (d["doc_date"], d["id"]))]
        out.append(row)

    totals = {"invoices": len(grand["invoices"]), "taxable": _f(grand["taxable"]),
              "cgst": _f(grand["cgst"]), "sgst": _f(grand["sgst"]), "igst": _f(grand["igst"]),
              "tax": _f(grand["cgst"] + grand["sgst"] + grand["igst"]),
              "total": _f(grand["total"]), "roundoff": _f(grand["roundoff"])}
    if group == "material":
        totals["line_total"] = _f(base_total)
        totals["qty"] = float(sum((r["qty"] for r in rows.values()), ZERO))
    return {"group": group, "rows": out, "totals": totals}
