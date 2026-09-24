"""Prices held before GST, or with GST already in them."""


def setup(c, inclusive=False):
    c.post("/api/hsn", json={"code": "998314", "descr": "IT", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    m = c.post("/api/materials", json={"code": "SRV", "descr": "Consulting",
        "price": 1180 if inclusive else 1000, "price_inclusive": inclusive,
        "hsn": "998314", "uom": "NOS", "stock_qty": 9999}).json()["id"]
    cu = c.post("/api/customers", json={"code": "C1", "name": "A", "party_type": "B2B",
        "bill_addr": "a", "bill_city": "b", "bill_state": "29",
        "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}]}).json()["id"]
    return m, cu


def test_the_flag_is_held_on_the_material(org, seed_ref):
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    assert c.get("/api/materials").json()[0]["price_inclusive"] is True


def test_exclusive_adds_the_tax_on_top(org, seed_ref):
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=False)
    t = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()["totals"]
    assert t["taxable"] == 1000.0 and t["cgst"] == 90.0 and t["sgst"] == 90.0
    assert t["total"] == 1180.0


def test_inclusive_carves_the_tax_out(org, seed_ref):
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    t = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]}).json()["totals"]
    assert t["taxable"] == 1000.0 and t["cgst"] == 90.0 and t["sgst"] == 90.0
    assert t["total"] == 1180.0          # exactly what was quoted


def test_the_customer_pays_the_quoted_figure_on_odd_numbers(org, seed_ref):
    """Taxable plus tax must equal the gross to the paisa, not to the rupee."""
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    for qty, price in [(3, 333.33), (7, 99.99), (11, 45.55), (2, 1234.56)]:
        t = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
            "lines": [{"material_id": m, "qty": qty, "price": price}]}).json()["totals"]
        gross = round(qty * price, 2)
        assert round(t["taxable"] + t["tax"], 2) == gross, (qty, price, t)


def test_the_split_still_follows_the_place_of_supply(org, seed_ref):
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    intra = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]}).json()["totals"]
    inter = c.post("/api/invoices", json={"doc_date": "2026-08-11", "customer_id": cu,
        "pos_state": "33",
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]}).json()["totals"]
    assert intra["cgst"] == 90.0 and intra["igst"] == 0
    assert inter["igst"] == 180.0 and inter["cgst"] == 0
    assert intra["taxable"] == inter["taxable"] == 1000.0
    assert intra["total"] == inter["total"] == 1180.0


def test_the_document_can_override_the_material(org, seed_ref):
    """Same material, same price, billed the other way round."""
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=False)       # material says exclusive
    excl = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]}).json()["totals"]
    incl = c.post("/api/invoices", json={"doc_date": "2026-08-11", "customer_id": cu,
        "price_mode": "INCL",
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]}).json()["totals"]
    assert excl["taxable"] == 1180.0 and excl["total"] == 1392.4   # 1180 + 18%
    assert incl["taxable"] == 1000.0 and incl["total"] == 1180.0


def test_a_line_can_override_on_its_own(org, seed_ref):
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=False)
    t = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1180,
                   "price_inclusive": True}]}).json()["totals"]
    assert t["taxable"] == 1000.0 and t["total"] == 1180.0


def test_the_basis_is_frozen_on_the_invoice(org, seed_ref):
    """Changing the material later must not re-interpret an issued invoice."""
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]}).json()
    c.put(f"/api/materials/{m}", json={"code": "SRV", "descr": "Consulting",
        "price": 1180, "price_inclusive": False, "hsn": "998314", "uom": "NOS",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    again = c.get(f"/api/invoices/{inv['id']}").json()["totals"]
    assert again["taxable"] == 1000.0 and again["total"] == 1180.0


def test_inclusive_and_exclusive_can_sit_on_one_invoice(org, seed_ref):
    c = org(); seed_ref(c)
    m1, cu = setup(c, inclusive=False)
    m2 = c.post("/api/materials", json={"code": "KIT", "descr": "Kit", "price": 1180,
        "price_inclusive": True, "hsn": "998314", "uom": "NOS",
        "stock_qty": 99}).json()["id"]
    t = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m1, "qty": 1, "price": 1000},
                  {"material_id": m2, "qty": 1, "price": 1180}]}).json()["totals"]
    assert t["taxable"] == 2000.0 and t["total"] == 2360.0
    kinds = sorted(l["inclusive"] for l in t["lines"])
    assert kinds == [False, True]


def test_the_hsn_summary_uses_the_taxable_value(org, seed_ref):
    """GSTR-1 wants the value before tax, whichever way the price was quoted."""
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    t = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 2, "price": 1180}]}).json()["totals"]
    assert sum(h["taxable"] for h in t["hsn"]) == t["taxable"] == 2000.0


def test_gstr1_reports_the_taxable_value_not_the_gross(org, seed_ref):
    c = org(); seed_ref(c)
    m, cu = setup(c, inclusive=True)
    c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1180}]})
    g = c.get("/api/returns/gstr1", params={"period": "2026-08"}).json()
    assert g["totals"]["taxable"] == 1000.0
    assert g["totals"]["cgst"] == 90.0 and g["totals"]["sgst"] == 90.0
