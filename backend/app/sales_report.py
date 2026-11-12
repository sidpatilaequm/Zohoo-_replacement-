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


# (key, name, section). Sections group the choices in the date-range picker.
PRESETS = [
    ("today", "Today", "This year"),
    ("this_week", "This week", "This year"),
    ("this_month", "This month", "This year"),
    ("this_quarter", "This quarter", "This year"),
    ("this_year", "This year", "This year"),
    ("yesterday", "Yesterday", "Previous period"),
    ("prev_week", "Previous week", "Previous period"),
    ("prev_month", "Previous month", "Previous period"),
    ("prev_quarter", "Previous quarter", "Previous period"),
    ("ly_today", "Same day last year", "Last year"),
    ("ly_week", "Same week last year", "Last year"),
    ("ly_month", "Same month last year", "Last year"),
    ("ly_quarter", "Same quarter last year", "Last year"),
    ("prev_year", "Last year", "Last year"),
    ("custom", "Custom dates", "Custom"),
]

# Each "last year" preset is its "this year" preset moved back one year.
LAST_YEAR_OF = {"ly_today": "today", "ly_week": "this_week",
                "ly_month": "this_month", "ly_quarter": "this_quarter"}
WEEK_KEYS = {"this_week", "prev_week", "ly_week"}

PRESET_KEYS = {k for k, _, _ in PRESETS}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ZERO = Decimal("0")


# ------------------------------------------------------------ date ranges
def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def _month_end(d: date) -> date:
    return d.replace(day=monthrange(d.year, d.month)[1])


def year_earlier(start: date, end: date, weekly: bool = False) -> tuple[date, date]:
    """The same period one year earlier, for comparison.

    Weeks move back 52 weeks so they still run Monday to Sunday. Everything
    else moves back 12 months. A range of whole months stays whole months, so
    February of a leap year compares with all of February the year before."""
    if weekly:
        return start - timedelta(weeks=52), end - timedelta(weeks=52)
    a, b = add_months(start, -12), add_months(end, -12)
    if start.day == 1 and end == _month_end(end):
        b = _month_end(b)
    return a, b


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


    if key in LAST_YEAR_OF:
        base = resolve_range(tenant, LAST_YEAR_OF[key], today)
        a, b = year_earlier(base["start"], base["end"], weekly=key == "ly_week")
        name = dict((k, n) for k, n, _ in PRESETS)[key]
        if key == "ly_today":
            detail = f"{a.day} {MON[a.month - 1]} {a.year}"
        elif key == "ly_week":
            detail = f"{a.day} {MON[a.month - 1]}–{b.day} {MON[b.month - 1]} {b.year}"
        elif key == "ly_month":
            detail = f"{MON[a.month - 1]} {a.year}"
        else:
            _, _, q, fy = _quarter_of(tenant, a)
            detail = f"Q{q} {_fy_text(fy)}, {MON[a.month - 1]}–{MON[b.month - 1]}"
        return {"key": key, "label": f"{name} ({detail})", "start": a, "end": b}

    if key == "today":
        a = b = today
        label = "Today"
    elif key == "yesterday":
        a = b = today - timedelta(days=1)
        label = "Yesterday"
    elif key in ("this_week", "prev_week"):
        a = today - timedelta(days=today.weekday())
        if key == "prev_week":
            a -= timedelta(days=7)
        b = a + timedelta(days=6)
        label = "This week" if key == "this_week" else "Previous week"
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
        label = f"{'This' if key == 'this_year' else 'Last'} year ({_fy_text(fy)})"
    return {"key": key, "label": label, "start": a, "end": b}


def all_ranges(tenant, today: date) -> list[dict]:
    out = []
    for k, name, section in PRESETS:
        if k == "custom":
            out.append({"key": k, "name": name, "section": section, "label": name,
                        "start": None, "end": None})
        else:
            r = resolve_range(tenant, k, today)
            out.append({"key": k, "name": name, "section": section, **r})
    return out


def comparison_range(r: dict, today: date) -> dict:
    """The same period a year before the range r.

    A period still running (this month, this year) is compared to date: this
    year so far against last year up to the same day, not against all of last
    year, which would make every unfinished period look like a fall."""
    weekly = r["key"] in WEEK_KEYS
    a, b = year_earlier(r["start"], r["end"], weekly=weekly)
    if r["start"] <= today < r["end"]:
        _, b = year_earlier(today, today, weekly=weekly)
        return {"key": "year_earlier", "label": "Same period a year earlier, to the same date",
                "start": a, "end": b, "to_date": True, "current_end": today}
    return {"key": "year_earlier", "label": "Same period a year earlier", "start": a, "end": b,
            "to_date": False}


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

    keys = {id(r): k for k, r in rows.items()}
    base_total = sum((r["total"] for r in rows.values()), ZERO)
    out = []
    for r in sorted(rows.values(), key=lambda x: (-x["total"], x.get("code") or x.get("name") or "")):
        row = {k: v for k, v in r.items() if k not in ("invoices", "docs")}
        row["key"] = keys[id(r)]
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


def _growth(now: float, before: float):
    if not before:
        return None
    return round((now - before) / abs(before) * 100, 1)


def with_comparison(cur: dict, prev: dict, prev_range: dict) -> dict:
    """Add last year's figures to each row of cur and to its totals.

    Rows that sold only in the earlier period are added with nothing this
    period, so a customer or material that stopped buying still shows."""
    before = {r["key"]: r for r in prev["rows"]}
    rows = []
    for r in cur["rows"]:
        p = before.pop(r["key"], None)
        rows.append({**r, "prev_total": p["total"] if p else 0.0,
                     "prev_invoices": p["invoice_count"] if p else 0,
                     "growth_pct": _growth(r["total"], p["total"] if p else 0.0)})
    for p in sorted(before.values(), key=lambda x: -x["total"]):
        blank = {k: (0.0 if isinstance(v, float) else v) for k, v in p.items()}
        blank.update(invoice_count=0, docs=[], share_pct=0.0, prev_total=p["total"],
                     prev_invoices=p["invoice_count"], growth_pct=-100.0, only_before=True)
        if "qty" in blank:
            blank["qty"] = 0.0
            blank["avg_price"] = None
        rows.append(blank)
    T, P = cur["totals"], prev["totals"]
    total_key = "line_total" if cur["group"] == "material" else "total"
    compare = {"range": prev_range, "totals": P,
               "growth_pct": _growth(T[total_key], P[total_key]),
               "invoices_change": T["invoices"] - P["invoices"]}
    return {**cur, "rows": rows, "compare": compare}
