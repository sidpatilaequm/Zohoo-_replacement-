"""v4.7: a customer's invoices and proformas from the customer list, and sales
reports with previous-week, same-period-last-year presets and a comparison
with a year earlier."""
from tests.test_api import cust, mat
from tests.test_v44_sales_reports import inv, report, _ranges


def _line(m, qty=1, price=100):
    return [{"material_id": m, "qty": qty, "price": price}]


# ------------------------------------------------------- customer transactions
def test_customer_list_counts_invoices_and_proformas(org):
    a = org()
    c1, c2, m = cust(a), cust(a, "C002", gstin="33AABCB1234M1Z8"), mat(a)
    t1 = inv(a, c1, _line(m))
    inv(a, c1, _line(m), d="2026-08-12")
    inv(a, c1, _line(m), doc_type="PRO")
    inv(a, c2, _line(m))
    a.post(f"/api/invoices/{t1['id']}/cancel", json={"reason": "wrong rate"})

    rows = {c["id"]: c for c in a.get("/api/customers").json()}
    assert (rows[c1]["invoice_count"], rows[c1]["invoice_cancelled"]) == (1, 1)
    assert rows[c1]["proforma_count"] == 1
    assert (rows[c2]["invoice_count"], rows[c2]["proforma_count"]) == (1, 0)


def test_invoice_list_filters_by_customer_and_dates(org):
    a = org()
    c1, c2, m = cust(a), cust(a, "C002", gstin="33AABCB1234M1Z8"), mat(a)
    inv(a, c1, _line(m), d="2026-05-02")
    inv(a, c1, _line(m), d="2026-08-12")
    inv(a, c1, _line(m), doc_type="PRO")
    inv(a, c2, _line(m))

    tax = a.get(f"/api/invoices?doc_type=TAX&customer_id={c1}").json()
    assert len(tax) == 2 and {v["customer_id"] for v in tax} == {c1}
    pro = a.get(f"/api/invoices?doc_type=PRO&customer_id={c1}").json()
    assert len(pro) == 1 and pro[0]["doc_type"] == "PRO"
    aug = a.get(f"/api/invoices?doc_type=TAX&customer_id={c1}"
                "&start=2026-08-01&end=2026-08-31").json()
    assert [v["doc_date"] for v in aug] == ["2026-08-12"]


# ------------------------------------------------------------------- ranges
def test_previous_week_and_last_year_presets(org):
    a = org()
    r = _ranges(a, "2026-08-13")                 # Thursday, Q2 FY 2026-27
    assert (r["prev_week"]["start"], r["prev_week"]["end"]) == ("2026-08-03", "2026-08-09")
    assert (r["ly_today"]["start"], r["ly_today"]["end"]) == ("2025-08-13", "2025-08-13")
    # 52 weeks back keeps Monday to Sunday
    assert (r["ly_week"]["start"], r["ly_week"]["end"]) == ("2025-08-11", "2025-08-17")
    assert (r["ly_month"]["start"], r["ly_month"]["end"]) == ("2025-08-01", "2025-08-31")
    assert (r["ly_quarter"]["start"], r["ly_quarter"]["end"]) == ("2025-07-01", "2025-09-30")
    assert (r["prev_year"]["start"], r["prev_year"]["end"]) == ("2025-04-01", "2026-03-31")
    assert "Q2 FY 2025-26" in r["ly_quarter"]["label"]
    assert {x["section"] for x in r.values()} == {"This year", "Previous period", "Last year", "Custom"}


def test_leap_february_compares_with_whole_february(org):
    a = org()
    r = _ranges(a, "2029-02-28")
    assert (r["ly_month"]["start"], r["ly_month"]["end"]) == ("2028-02-01", "2028-02-29")
    assert (r["ly_today"]["start"], r["ly_today"]["end"]) == ("2028-02-28", "2028-02-28")


# --------------------------------------------------------------- comparison
def test_compare_with_a_year_earlier(org):
    a = org()
    c1, c2, c3, m = cust(a), cust(a, "C002", gstin="33AABCB1234M1Z8"), cust(a, "C003", gstin="33AABCG1234M1Z8"), mat(a)
    inv(a, c1, _line(m, 2, 100), d="2026-08-10")   # this year
    inv(a, c1, _line(m, 1, 100), d="2025-08-10")   # last year
    inv(a, c2, _line(m, 1, 100), d="2026-08-11")   # new this year
    inv(a, c3, _line(m, 3, 100), d="2025-08-20")   # bought only last year

    d = report(a, "customer", start="2026-08-01", end="2026-08-31")
    assert "compare" not in d
    r = a.get("/api/reports/sales?group=customer&range=custom&start=2026-08-01"
              "&end=2026-08-31&compare=true").json()
    assert (r["compare"]["range"]["start"], r["compare"]["range"]["end"]) == ("2025-08-01", "2025-08-31")
    rows = {x["key"]: x for x in r["rows"]}
    one, two, three = rows[f"c{c1}"], rows[f"c{c2}"], rows[f"c{c3}"]
    assert one["prev_total"] == one["total"] / 2 and one["growth_pct"] == 100.0
    assert two["prev_total"] == 0 and two["growth_pct"] is None
    assert three.get("only_before") and three["total"] == 0 and three["growth_pct"] == -100.0
    assert three["invoice_count"] == 0 and three["prev_invoices"] == 1
    assert r["totals"]["invoices"] == 2 and r["compare"]["totals"]["invoices"] == 2
    assert r["compare"]["invoices_change"] == 0


def test_material_compare_and_row_keys(org):
    a = org()
    c, m = cust(a), mat(a)
    inv(a, c, _line(m, 4, 50), d="2026-08-10")
    inv(a, c, _line(m, 2, 50), d="2025-08-10")
    r = a.get("/api/reports/sales?group=material&range=this_month&today=2026-08-15&compare=true").json()
    row = r["rows"][0]
    assert row["key"] == f"m{m}" and row["qty"] == 4
    assert row["growth_pct"] == 100.0
    assert r["compare"]["growth_pct"] == 100.0


def test_running_period_compares_to_date(org):
    """This year so far is compared with last year up to the same day."""
    a = org()
    c, m = cust(a), mat(a)
    inv(a, c, _line(m, 1, 100), d="2026-06-10")    # this FY, before today
    inv(a, c, _line(m, 1, 100), d="2025-06-10")    # last FY, same point
    inv(a, c, _line(m, 5, 100), d="2026-01-15")    # last FY, after the same point
    r = a.get("/api/reports/sales?group=customer&range=this_year&today=2026-08-13&compare=true").json()
    cr = r["compare"]["range"]
    assert (cr["start"], cr["end"], cr["to_date"]) == ("2025-04-01", "2025-08-13", True)
    assert r["compare"]["growth_pct"] == 0.0
    # A finished period compares in full.
    r = a.get("/api/reports/sales?group=customer&range=prev_year&today=2026-08-13&compare=true").json()
    assert (r["compare"]["range"]["start"], r["compare"]["range"]["end"]) == ("2024-04-01", "2025-03-31")
    assert r["compare"]["range"]["to_date"] is False
