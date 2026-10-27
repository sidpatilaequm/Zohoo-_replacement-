"""v4.4 sales reports: by customer, by material and by employee (who created the
invoice), over preset and custom date ranges."""
from datetime import date

from tests.test_api import cust, mat


def inv(c, cid, lines, d="2026-08-10", doc_type="TAX"):
    r = c.post("/api/invoices", json={"doc_date": d, "customer_id": cid, "doc_type": doc_type,
                                      "lines": lines})
    assert r.status_code == 201, r.text
    return r.json()


def report(c, group, rng="custom", start="2026-04-01", end="2027-03-31", today=None):
    q = f"/api/reports/sales?group={group}&range={rng}"
    if start:
        q += f"&start={start}"
    if end:
        q += f"&end={end}"
    if today:
        q += f"&today={today}"
    r = c.get(q)
    assert r.status_code == 200, r.text
    return r.json()


def second_user(api, a, email="sales@x.co", group="Sales"):
    from tests.conftest import Client
    gid = [g for g in a.get("/api/groups").json() if g["name"] == group][0]["id"]
    r = a.post("/api/users", json={"name": "Priya Sales", "email": email,
                                   "password": "correct horse", "group_id": gid})
    assert r.status_code in (200, 201), r.text
    tok = api.post("/api/auth/signin", json={"email": email, "password": "correct horse"}).json()["token"]
    return Client(api, tok, a.tid)


# ------------------------------------------------------------- ranges
def _ranges(c, today):
    return {r["key"]: r for r in c.get(f"/api/reports/sales/ranges?today={today}").json()}


def test_preset_ranges_follow_the_financial_year(org):
    a = org()
    r = _ranges(a, "2026-08-13")                # a Thursday in Q2 of FY 2026-27
    assert (r["today"]["start"], r["today"]["end"]) == ("2026-08-13", "2026-08-13")
    assert (r["this_week"]["start"], r["this_week"]["end"]) == ("2026-08-10", "2026-08-16")
    assert (r["this_month"]["start"], r["this_month"]["end"]) == ("2026-08-01", "2026-08-31")
    assert (r["prev_month"]["start"], r["prev_month"]["end"]) == ("2026-07-01", "2026-07-31")
    assert (r["this_quarter"]["start"], r["this_quarter"]["end"]) == ("2026-07-01", "2026-09-30")
    assert (r["prev_quarter"]["start"], r["prev_quarter"]["end"]) == ("2026-04-01", "2026-06-30")
    assert (r["this_year"]["start"], r["this_year"]["end"]) == ("2026-04-01", "2027-03-31")
    assert (r["prev_year"]["start"], r["prev_year"]["end"]) == ("2025-04-01", "2026-03-31")
    assert "Q2 FY 2026-27" in r["this_quarter"]["label"]


def test_ranges_cross_year_boundaries(org):
    a = org()
    r = _ranges(a, "2027-01-05")                # Q4 of FY 2026-27, a new calendar year
    assert (r["this_quarter"]["start"], r["this_quarter"]["end"]) == ("2027-01-01", "2027-03-31")
    assert (r["prev_quarter"]["start"], r["prev_quarter"]["end"]) == ("2026-10-01", "2026-12-31")
    assert (r["prev_month"]["start"], r["prev_month"]["end"]) == ("2026-12-01", "2026-12-31")
    assert r["this_year"]["start"] == "2026-04-01"
    r = _ranges(a, "2026-04-02")                # Q1: the previous quarter is in last FY
    assert (r["prev_quarter"]["start"], r["prev_quarter"]["end"]) == ("2026-01-01", "2026-03-31")
    assert r["prev_year"]["start"] == "2025-04-01"


def test_custom_range_is_checked(org):
    a = org()
    assert a.get("/api/reports/sales?group=customer&range=custom&start=2026-05-01").status_code == 422
    r = a.get("/api/reports/sales?group=customer&range=custom&start=2026-05-02&end=2026-05-01")
    assert r.status_code == 422 and "after the end date" in r.text
    assert a.get("/api/reports/sales?group=nothing&range=this_month").status_code == 422
    assert a.get("/api/reports/sales?group=customer&range=someday").status_code == 422


# ------------------------------------------------------------- reports
def test_sales_by_customer_counts_only_live_tax_invoices_in_range(org):
    a = org(state="29")
    m = mat(a, price=1000)
    c1 = cust(a, "C1", "29", "29AAACT1234N1Z2")
    c2 = cust(a, "C2", "33", "33AABCK1234M1Z8")
    inv(a, c1, [{"material_id": m, "qty": 2}], "2026-08-10")       # 2000 + 18% = 2360
    inv(a, c1, [{"material_id": m, "qty": 1}], "2026-08-20")       # 1000 + 18% = 1180
    inv(a, c2, [{"material_id": m, "qty": 5}], "2026-08-15")       # 5000 + 18% = 5900
    inv(a, c2, [{"material_id": m, "qty": 9}], "2026-08-16", "PRO")  # proforma: not a sale
    gone = inv(a, c1, [{"material_id": m, "qty": 3}], "2026-08-17")
    assert a.post(f"/api/invoices/{gone['id']}/cancel", json={"reason": "Raised in error"}).status_code == 200
    inv(a, c1, [{"material_id": m, "qty": 4}], "2026-09-01")       # outside the range

    d = report(a, "customer", start="2026-08-01", end="2026-08-31")
    rows = {r["code"]: r for r in d["rows"]}
    assert [r["code"] for r in d["rows"]] == ["C2", "C1"]          # largest first
    assert rows["C1"]["invoice_count"] == 2 and rows["C1"]["taxable"] == 3000 and rows["C1"]["total"] == 3540
    assert rows["C1"]["cgst"] == 270 and rows["C1"]["igst"] == 0
    assert rows["C2"]["igst"] == 900 and rows["C2"]["total"] == 5900
    assert d["totals"] == {**d["totals"], "invoices": 3, "taxable": 8000, "tax": 1440, "total": 9440}
    assert round(sum(r["share_pct"] for r in d["rows"])) == 100
    assert [x["doc_date"] for x in rows["C1"]["docs"]] == ["2026-08-10", "2026-08-20"]


def test_sales_by_material_uses_lines(org):
    a = org(state="29")
    m1 = mat(a, "LIC-A", price=1000)
    m2 = mat(a, "LIC-B", price=250)
    c = cust(a, "C1", "29", "29AAACT1234N1Z2")
    inv(a, c, [{"material_id": m1, "qty": 2}, {"material_id": m2, "qty": 4}], "2026-08-10")
    inv(a, c, [{"material_id": m1, "qty": 1}], "2026-08-11")
    d = report(a, "material", "this_month", None, None, today="2026-08-25")
    assert d["range"]["start"] == "2026-08-01" and d["range"]["end"] == "2026-08-31"
    rows = {r["code"]: r for r in d["rows"]}
    assert rows["LIC-A"]["qty"] == 3 and rows["LIC-A"]["taxable"] == 3000 and rows["LIC-A"]["total"] == 3540
    assert rows["LIC-A"]["invoice_count"] == 2 and rows["LIC-A"]["avg_price"] == 1000
    assert rows["LIC-B"]["qty"] == 4 and rows["LIC-B"]["taxable"] == 1000 and rows["LIC-B"]["uom"] == "LIC"
    assert d["totals"]["qty"] == 7 and d["totals"]["line_total"] == 4720 and d["totals"]["total"] == 4720


def test_sales_by_employee_uses_who_created_the_invoice(api, org, seed_ref):
    a = org(state="29")
    m = mat(a, price=1000)
    c = cust(a, "C1", "29", "29AAACT1234N1Z2")
    s = second_user(api, a)
    # The second user is also on the employee master, matched by e-mail.
    assert a.post("/api/employees", json={"emp_code": "EMP007", "first_name": "Priya",
                                          "last_name": "Rao", "email": "Sales@X.co"}).status_code == 201
    inv(a, c, [{"material_id": m, "qty": 1}], "2026-08-10")       # by the admin
    inv(s, c, [{"material_id": m, "qty": 3}], "2026-08-11")       # by Priya
    inv(s, c, [{"material_id": m, "qty": 2}], "2026-08-12")

    # An invoice saved before v4.4 has no creator on file.
    from app.db import SessionLocal
    from app import models as M
    db = SessionLocal()
    old = inv(a, c, [{"material_id": m, "qty": 1}], "2026-08-13")
    db.get(M.Invoice, old["id"]).created_by_user_id = None
    db.commit(); db.close()

    d = report(a, "employee", start="2026-08-01", end="2026-08-31")
    rows = {r["name"]: r for r in d["rows"]}
    assert rows["Priya Sales"]["invoice_count"] == 2 and rows["Priya Sales"]["taxable"] == 5000
    assert rows["Priya Sales"]["emp_code"] == "EMP007" and rows["Priya Sales"]["emp_name"] == "Priya Rao"
    assert rows["Admin"]["invoice_count"] == 1 and rows["Admin"]["emp_code"] is None
    assert rows["Not recorded"]["invoice_count"] == 1 and rows["Not recorded"]["user_id"] is None
    assert d["totals"]["invoices"] == 4


def test_reports_need_the_reports_permission_and_stay_in_the_tenant(api, org):
    a = org(state="29", email="a@x.co", name="A")
    b = org(state="29", email="b@x.co", name="B")
    m = mat(a, price=1000)
    c = cust(a, "C1", "29", "29AAACT1234N1Z2")
    inv(a, c, [{"material_id": m, "qty": 1}], "2026-08-10")
    assert report(b, "customer")["rows"] == []                    # another organisation sees nothing
    r = a.post("/api/groups", json={"name": "Billing only", "perms": ["invoice", "saved"]})
    assert r.status_code in (200, 201), r.text
    s = second_user(api, a, "noreports@x.co", "Billing only")
    assert s.get("/api/reports/sales?group=customer&range=this_month").status_code == 403
    assert s.get("/api/reports/sales/ranges").status_code == 403
