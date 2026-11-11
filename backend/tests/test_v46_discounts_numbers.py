"""v4.6 — line and overall discounts on sales invoices and proformas, the
line items on the print-out, and document numbers typed by hand that must
not repeat within a financial year."""
import io
import pdfplumber
from .test_api import cust

ORG = {"name": "Aequm India Private Limited", "state_code": "29"}


def _mat(c, code="M1", price=1000, incl=False):
    r = c.post("/api/materials", json={
        "code": code, "descr": f"Item {code}", "price": price, "cost": price,
        "hsn": "998314", "stock_qty": 1000, "uom": "LIC", "price_inclusive": incl,
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _setup(org, **extra):
    a = org(name=ORG["name"])
    r = a.put("/api/org", json={**ORG, **extra})
    assert r.status_code == 200, r.text
    # same state as the organisation: CGST + SGST
    c = cust(a, state="29", gstin="29AAACT1234N1Z2")
    return a, c


def _post(a, c, lines, status=201, **kw):
    body = {"doc_date": "2026-10-01", "customer_id": c, "lines": lines}
    body.update(kw)
    r = a.post("/api/invoices", json=body)
    assert r.status_code == status, r.text
    return r.json()


def _pdf(a, iid):
    r = a.get(f"/api/print/invoices/{iid}.pdf")
    assert r.status_code == 200, r.text
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


# ============================================================ discounts
def test_line_percentage_discount_comes_off_before_tax(org):
    a, c = _setup(org)
    m = _mat(a)
    t = _post(a, c, [{"material_id": m, "qty": 2, "disc_type": "PCT", "disc_value": 10}])["totals"]
    assert t["gross"] == 2000 and t["discount"] == 200 and t["taxable"] == 1800
    assert t["cgst"] == 162 and t["sgst"] == 162 and t["rounded"] == 2124
    L = t["lines"][0]
    assert L["value"] == 2000 and L["discount"] == 200 and L["amount"] == 1800
    assert L["disc_type"] == "PCT" and L["disc_value"] == 10 and L["total"] == 2124


def test_line_amount_discount(org):
    a, c = _setup(org)
    m = _mat(a)
    t = _post(a, c, [{"material_id": m, "qty": 1, "disc_type": "AMT", "disc_value": 150.5}])["totals"]
    assert t["taxable"] == 849.5 and t["discount"] == 150.5


def test_overall_percentage_discount_is_spread_over_the_lines(org):
    a, c = _setup(org)
    m1, m2 = _mat(a, "M1", 1000), _mat(a, "M2", 500)
    t = _post(a, c, [{"material_id": m1, "qty": 1}, {"material_id": m2, "qty": 1}],
              disc_type="PCT", disc_value=10)["totals"]
    assert t["overall_discount"] == 150 and t["taxable"] == 1350
    assert [L["amount"] for L in t["lines"]] == [900, 450]
    assert t["disc_type"] == "PCT" and t["disc_value"] == 10


def test_overall_amount_discount_shares_add_up_to_the_paisa(org):
    a, c = _setup(org)
    ms = [_mat(a, f"M{k}", 100) for k in range(3)]
    t = _post(a, c, [{"material_id": m, "qty": 1} for m in ms],
              disc_type="AMT", disc_value=100)["totals"]
    shares = [L["overall_disc"] for L in t["lines"]]
    assert round(sum(shares), 2) == 100          # 33.33 + 33.33 + 33.34
    assert t["taxable"] == 200 and t["discount"] == 100
    # tax is worked out per line on what is left of each
    assert round(sum(L["cgst"] for L in t["lines"]), 2) == t["cgst"]


def test_line_and_overall_discounts_together(org):
    a, c = _setup(org)
    m1, m2 = _mat(a, "M1", 1000), _mat(a, "M2", 1000)
    t = _post(a, c, [{"material_id": m1, "qty": 1, "disc_type": "PCT", "disc_value": 50},
                     {"material_id": m2, "qty": 1}],
              disc_type="AMT", disc_value=300)["totals"]
    # after line discounts: 500 and 1000; 300 shared 100 / 200
    assert [L["overall_disc"] for L in t["lines"]] == [100, 200]
    assert [L["amount"] for L in t["lines"]] == [400, 800]
    assert t["line_discount"] == 500 and t["overall_discount"] == 300
    assert t["gross"] - t["discount"] == t["taxable"] == 1200


def test_discount_on_a_gst_inclusive_line(org):
    a, c = _setup(org)
    m = _mat(a, price=1180, incl=True)
    t = _post(a, c, [{"material_id": m, "qty": 1, "disc_type": "PCT", "disc_value": 10}])["totals"]
    # 10% off the quoted 1,180 is 1,062 with GST in it: 900 + 162
    assert t["taxable"] == 900 and t["tax"] == 162 and t["rounded"] == 1062
    L = t["lines"][0]
    assert L["unit_rate"] == 1000 and L["value"] == 1000 and L["discount"] == 100


def test_discounts_are_checked(org):
    a, c = _setup(org)
    m = _mat(a)
    line = {"material_id": m, "qty": 1}
    _post(a, c, [{**line, "disc_type": "PCT", "disc_value": 101}], status=422)
    _post(a, c, [{**line, "disc_type": "PCT", "disc_value": -5}], status=422)
    _post(a, c, [{**line, "disc_type": "AMT", "disc_value": 1000.01}], status=422)
    _post(a, c, [{**line, "disc_type": "AMT", "disc_value": 1.005}], status=422)
    _post(a, c, [{**line, "disc_value": 5}], status=422)          # type missing
    _post(a, c, [line], disc_type="AMT", disc_value=1001, status=422)
    _post(a, c, [line], disc_type="PCT", disc_value=100, status=422)  # nil invoice
    # a zero discount with no type is simply no discount
    assert _post(a, c, [{**line, "disc_value": 0}])["totals"]["discount"] == 0


def test_discounts_are_kept_edited_and_carried_on_conversion(org):
    a, c = _setup(org)
    m = _mat(a)
    pro = _post(a, c, [{"material_id": m, "qty": 2, "disc_type": "AMT", "disc_value": 100}],
                doc_type="PRO", disc_type="PCT", disc_value=5)
    v = a.get(f"/api/invoices/{pro['id']}").json()["invoice"]
    assert v["disc_type"] == "PCT" and v["disc_value"] == 5
    assert v["lines"][0]["disc_type"] == "AMT" and v["lines"][0]["disc_value"] == 100

    r = a.put(f"/api/invoices/{pro['id']}", json={
        "doc_type": "PRO", "doc_date": "2026-10-01", "customer_id": c,
        "lines": [{"material_id": m, "qty": 2, "disc_type": "PCT", "disc_value": 20}]})
    assert r.status_code == 200, r.text
    assert r.json()["totals"]["taxable"] == 1600 and r.json()["totals"]["overall_discount"] == 0

    tax = a.post(f"/api/invoices/{pro['id']}/convert?doc_date=2026-10-02").json()
    assert tax["totals"]["taxable"] == 1600
    assert a.get(f"/api/invoices/{tax['id']}").json()["invoice"]["lines"][0]["disc_value"] == 20


def test_registers_and_returns_carry_the_discounted_value(org):
    a, c = _setup(org)
    m = _mat(a)
    _post(a, c, [{"material_id": m, "qty": 1}], disc_type="PCT", disc_value=10)
    row = a.get("/api/invoices").json()[0]
    assert row["taxable"] == 900 and row["gross"] == 1000 and row["discount"] == 100
    margin = a.get("/api/returns/reports/margin").json()
    assert margin[0]["sales_value"] == 900


def test_print_shows_clear_line_items_and_the_discount(org):
    a, c = _setup(org)
    m1, m2 = _mat(a, "M1", 1000), _mat(a, "M2", 500)
    inv = _post(a, c, [{"material_id": m1, "qty": 2, "disc_type": "PCT", "disc_value": 10},
                       {"material_id": m2, "qty": 1}], disc_type="AMT", disc_value=100)
    t = _pdf(a, inv["id"])
    assert "Discount" in t and "Taxable Value" in t and "LIC" in t
    assert "Items Total 2,500.00" in t
    assert f"Less: Discount (-) {inv['totals']['discount']:,.2f}" in t
    assert f"Sub Total {inv['totals']['taxable']:,.2f}" in t
    assert "taken off before GST" in t and "overall discount" in t


def test_print_without_discount_has_no_discount_column(org):
    a, c = _setup(org)
    inv = _post(a, c, [{"material_id": _mat(a), "qty": 1}])
    t = _pdf(a, inv["id"])
    assert "Discount" not in t and "Items Total" not in t and "Sub Total 1,000.00" in t


def test_print_inclusive_line_shows_rate_without_gst_and_the_quoted_price(org):
    a, c = _setup(org)
    inv = _post(a, c, [{"material_id": _mat(a, price=1180, incl=True), "qty": 1}])
    t = _pdf(a, inv["id"])
    assert "1,180.00\nincl. GST" in t and "1 Item M1 998314 1 1,000.00" in t


# ======================================================= document numbers
def test_a_number_can_be_typed_by_hand(org):
    a, c = _setup(org)
    m = _mat(a)
    d = _post(a, c, [{"material_id": m, "qty": 1}], doc_no="  AEQ/OCT/7 ")
    assert d["doc_no"] == "AEQ/OCT/7" and d["fy"] == "2026-27"
    # the automatic series is untouched
    assert _post(a, c, [{"material_id": m, "qty": 1}])["doc_no"] == "INV/001"


def test_a_number_cannot_repeat_within_the_financial_year(org):
    a, c = _setup(org)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    _post(a, c, line, doc_no="X-1", doc_date="2026-04-01")
    r = _post(a, c, line, doc_no="X-1", doc_date="2027-03-31", status=409)
    assert "2026-27" in r["detail"]
    _post(a, c, line, doc_no="x-1", doc_date="2026-12-01", status=409)   # case is ignored
    # the next financial year may use it again
    assert _post(a, c, line, doc_no="X-1", doc_date="2027-04-01")["fy"] == "2027-28"
    # and a proforma is its own series
    _post(a, c, line, doc_no="X-1", doc_type="PRO", doc_date="2026-05-01")


def test_financial_year_follows_the_company_start(org):
    a, c = _setup(org, fy_start_month=1, fy_start_day=1)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    _post(a, c, line, doc_no="J-1", doc_date="2026-12-31")
    assert _post(a, c, line, doc_no="J-1", doc_date="2027-01-01")["fy"] == "2027"


def test_check_number_endpoint(org):
    a, c = _setup(org)
    m = _mat(a)
    inv = _post(a, c, [{"material_id": m, "qty": 1}], doc_no="K-9")
    q = "/api/invoices/check-no?doc_type=TAX&doc_no=K-9"
    r = a.get(q + "&doc_date=2026-10-10").json()
    assert r["available"] is False and r["taken_by"]["id"] == inv["id"] and r["fy"] == "2026-27"
    assert a.get(q + "&doc_date=2027-10-10").json()["available"] is True
    assert a.get(q + f"&doc_date=2026-10-10&exclude_id={inv['id']}").json()["available"] is True


def test_automatic_series_steps_over_hand_typed_numbers(org):
    a, c = _setup(org)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    _post(a, c, line, doc_no="INV/001")
    _post(a, c, line, doc_no="INV/002")
    assert a.get("/api/invoices/next-no?doc_type=TAX&doc_date=2026-10-01").json()["doc_no"] == "INV/003"
    assert _post(a, c, line)["doc_no"] == "INV/003"
    assert _post(a, c, line)["doc_no"] == "INV/004"


def test_automatic_series_with_financial_year_numbering(org):
    a, c = _setup(org, inv_fy=True, fy_start_month=4, fy_start_day=1)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    _post(a, c, line, doc_no="INV/2026-27/001")
    assert _post(a, c, line)["doc_no"] == "INV/2026-27/002"
    assert _post(a, c, line, doc_date="2027-05-01")["doc_no"] == "INV/2027-28/001"


def test_editing_can_renumber_but_not_onto_a_used_number(org):
    a, c = _setup(org)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    one = _post(a, c, line, doc_no="E-1")
    _post(a, c, line, doc_no="E-2")
    body = {"doc_type": "TAX", "doc_date": "2026-10-01", "customer_id": c, "lines": line}
    assert a.put(f"/api/invoices/{one['id']}", json={**body, "doc_no": "E-2"}).status_code == 409
    r = a.put(f"/api/invoices/{one['id']}", json={**body, "doc_no": "E-1A"})
    assert r.status_code == 200 and r.json()["doc_no"] == "E-1A"
    # leaving the number out keeps it
    r = a.put(f"/api/invoices/{one['id']}", json=body)
    assert r.json()["doc_no"] == "E-1A"
    # moving the date into another year re-checks the number there
    _post(a, c, line, doc_no="E-1A", doc_date="2027-06-01")
    assert a.put(f"/api/invoices/{one['id']}",
                 json={**body, "doc_date": "2027-06-02"}).status_code == 409


def test_conversion_takes_a_typed_number_and_checks_it(org):
    a, c = _setup(org)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    _post(a, c, line, doc_no="T-1")
    pro = _post(a, c, line, doc_type="PRO")
    assert a.post(f"/api/invoices/{pro['id']}/convert?doc_no=T-1").status_code == 409
    r = a.post(f"/api/invoices/{pro['id']}/convert?doc_no=T-2")
    assert r.status_code == 200 and r.json()["doc_no"] == "T-2"


def test_deleting_a_converted_invoice_reopens_the_right_proforma(org):
    """Numbers can now repeat across years, so the link is followed, not the number."""
    a, c = _setup(org)
    m = _mat(a)
    line = [{"material_id": m, "qty": 1}]
    p1 = _post(a, c, line, doc_type="PRO", doc_no="P-1", doc_date="2026-05-01")
    p2 = _post(a, c, line, doc_type="PRO", doc_no="P-1", doc_date="2027-05-01")
    a.post(f"/api/invoices/{p1['id']}/convert")
    t2 = a.post(f"/api/invoices/{p2['id']}/convert").json()
    assert a.delete(f"/api/invoices/{t2['id']}").status_code == 204
    pros = {p["id"]: p for p in a.get("/api/invoices?doc_type=PRO").json()}
    assert pros[p1["id"]]["converted_to_id"] and not pros[p2["id"]]["converted_to_id"]
