"""Goods receipt, discrepancy, counting, ordering and the stock ledger."""
import pytest


def trading(org, **kw):
    c = org(**kw)
    o = c.get("/api/org").json()
    c.put("/api/org", json={**{k: o[k] for k in
        ["name","gstin","pan","addr","city","state_code","pin","inv_prefix",
         "inv_seq","po_prefix","po_seq","bank"]}, "company_type": "TRADING"})
    return c


def mat(c, code="PHM-A", batch=False, shelf=0, cost=70, price=100, stock=0):
    r = c.post("/api/materials", json={"code": code, "descr": code, "price": price,
        "cost": cost, "hsn": "30049099", "stock_qty": stock, "uom": "NOS",
        "batch_managed": batch, "shelf_life_days": shelf,
        "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def vend(c, code="V001"):
    return c.post("/api/vendors", json={"code": code, "name": "Vendor " + code,
        "party_type": "B2B", "addr": "St", "city": "C", "state_code": "33",
        "gstins": [{"gstin": "33AAACR1234K1Z5", "is_default": True}]}).json()["id"]


def cust(c, code="C001"):
    return c.post("/api/customers", json={"code": code, "name": "Customer " + code,
        "party_type": "B2B", "bill_addr": "St", "bill_city": "C", "bill_state": "33",
        "gstins": [{"gstin": "33AABCK1234M1Z8", "is_default": True}]}).json()["id"]


def po(c, vid, mid, qty=500, price=70):
    return c.post("/api/purchase-orders", json={"doc_date": "2026-09-01",
        "vendor_id": vid, "lines": [{"material_id": mid, "qty": qty, "price": price}]}).json()["id"]


# ------------------------------------------------------ business type
def test_non_trading_cannot_touch_stock(org):
    c = org()
    assert c.get("/api/org").json()["company_type"] == "NONTRADING"
    r = c.get("/api/stock/summary")
    assert r.status_code == 409 and "non-trading" in r.text


def test_trading_opens_the_stock_screens(org):
    c = trading(org)
    assert c.get("/api/org").json()["company_type"] == "TRADING"
    assert c.get("/api/stock/summary").status_code == 200


# --------------------------------------------------------- attributes
def test_list_attribute_needs_values(org):
    c = org()
    r = c.post("/api/attributes", json={"code": "BRAND", "name": "Brand",
        "attr_type": "LIST", "values": []})
    assert r.status_code == 422 and "at least one value" in r.text


def test_attribute_value_is_checked_on_the_material(org):
    c = org()
    a = c.post("/api/attributes", json={"code": "BRAND", "name": "Brand",
        "attr_type": "LIST", "values": ["Abbott", "Generic"]}).json()["id"]
    ok = c.post("/api/materials", json={"code": "M1", "descr": "M1", "price": 10,
        "hsn": "3004", "uom": "NOS", "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12,
        "attributes": {str(a): "Abbott"}})
    assert ok.status_code == 201
    bad = c.post("/api/materials", json={"code": "M2", "descr": "M2", "price": 10,
        "hsn": "3004", "uom": "NOS", "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12,
        "attributes": {str(a): "Pfizer"}})
    assert bad.status_code == 422 and "not a permitted value" in bad.text


def test_attributes_are_shared_across_organisations(org):
    a = org(name="One", email="one@x.co")
    b = org(name="Two", email="two@x.co")
    a.post("/api/attributes", json={"code": "STORAGE", "name": "Storage",
        "attr_type": "LIST", "values": ["Ambient"]})
    assert [x["code"] for x in b.get("/api/attributes").json()] == ["STORAGE"]


# ------------------------------------------------------ goods receipt
def test_batch_material_needs_a_batch_number(org):
    c = trading(org); m = mat(c, batch=True, shelf=730); v = vend(c); p = po(c, v, m)
    r = c.post("/api/grn", json={"doc_no": "GRN1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 500}]})
    assert r.status_code == 422 and "batch number is required" in r.text


def test_expiry_is_manufacturing_date_plus_shelf_life(org):
    c = trading(org); m = mat(c, batch=True, shelf=730); v = vend(c); p = po(c, v, m)
    r = c.post("/api/grn", json={"doc_no": "GRN1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 500, "batch": "B1", "mfg_date": "2026-06-15"}]})
    assert r.status_code == 201
    assert r.json()["lines"][0]["exp_date"] == "2028-06-14"


def test_cannot_receive_more_than_the_order(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=100)
    r = c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 150}]})
    assert r.status_code == 422 and "remain open" in r.text


def test_only_owned_stock_raises_the_sellable_figure(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=1000)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p, "lines": [
        {"material_id": m, "qty": 500, "stock_type": "NORMAL"},
        {"material_id": m, "qty": 120, "stock_type": "RESERVED"},
        {"material_id": m, "qty": 15, "stock_type": "DAMAGED"},
        {"material_id": m, "qty": 300, "stock_type": "CONSIGNMENT"}]})
    # 935 received in total but only the 635 owned raises the material quantity
    assert c.get("/api/materials").json()[0]["stock_qty"] == 635
    s = c.get("/api/stock/summary").json()[0]
    assert s["consignment"] == 300 and s["owned"] == 635 and s["received"] == 935


# ------------------------------------------------------- discrepancy
def test_short_delivery_is_held_and_blocks_invoicing(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=500)
    r = c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 470}]}).json()
    assert r["discrepancies"][0]["difference"] == -30
    inv = c.get("/api/discrepancies/invoiceable").json()[0]
    assert inv["ordered"] == 500 and inv["delivered"] == 470
    assert inv["held"] == 470 and inv["invoiceable"] == 0


def test_release_makes_the_received_quantity_invoiceable(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=500)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 470}]})
    d = c.get("/api/discrepancies", params={"status": "HELD"}).json()[0]
    out = c.post(f"/api/discrepancies/{d['id']}/release").json()
    assert out["invoiceable_now"] == 470          # the received quantity, not the ordered 500
    inv = c.get("/api/discrepancies/invoiceable").json()[0]
    assert inv["held"] == 0 and inv["invoiceable"] == 470


def test_matching_delivery_raises_no_discrepancy(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=500)
    r = c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 500}]}).json()
    assert r["discrepancies"] == []
    assert c.get("/api/discrepancies").json() == []


# ------------------------------------------------ physical inventory
def test_count_posts_only_the_difference(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=500)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 500}]})
    sheet = c.get("/api/physical/sheet").json()
    assert sheet[0]["book_qty"] == 500
    r = c.post("/api/physical", json={"doc_no": "PI1", "count_date": "2026-09-10",
        "counted_by": "Store", "reason": "cycle count",
        "lines": [{"material_id": m, "stock_type": "NORMAL", "counted_qty": 488}]})
    assert r.status_code == 201 and r.json()["posted"][0]["difference"] == -12
    assert c.get("/api/materials").json()[0]["stock_qty"] == 488


def test_count_that_agrees_posts_nothing(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=500)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-05", "po_id": p,
        "lines": [{"material_id": m, "qty": 500}]})
    r = c.post("/api/physical", json={"doc_no": "PI1", "count_date": "2026-09-10",
        "lines": [{"material_id": m, "stock_type": "NORMAL", "counted_qty": 500}]})
    assert r.status_code == 422 and "nothing to post" in r.text


# ---------------------------------------------------------- ordering
def test_order_delivery_and_goods_issue(org):
    c = trading(org); m = mat(c, batch=True, shelf=365); v = vend(c); cu = cust(c)
    p = po(c, v, m, qty=800)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-01", "po_id": p, "lines": [
        {"material_id": m, "qty": 500, "batch": "B1", "mfg_date": "2026-01-10"},
        {"material_id": m, "qty": 300, "batch": "B2", "mfg_date": "2026-05-10"}]})
    so = c.post("/api/sales-orders", json={"doc_date": "2026-09-02", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 180}]}).json()
    assert so["short"] == []
    sug = c.get(f"/api/deliveries/suggest/{so['id']}").json()
    # earliest expiry first: B1 was made in January, so it goes before B2
    assert sug["lines"][0]["suggested"][0]["batch"] == "B1"
    d = c.post("/api/deliveries", json={"doc_date": "2026-09-05", "so_id": so["id"],
        "picks": [{"material_id": m, "batch": "B1", "stock_type": "NORMAL", "qty": 180}]})
    assert d.status_code == 201 and d.json()["order_status"] == "DELIVERED"
    assert c.get("/api/materials").json()[0]["stock_qty"] == 620


def test_cannot_pick_more_than_a_batch_holds(org):
    c = trading(org); m = mat(c, batch=True, shelf=365); v = vend(c); cu = cust(c)
    p = po(c, v, m, qty=100)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-01", "po_id": p,
        "lines": [{"material_id": m, "qty": 100, "batch": "B1", "mfg_date": "2026-01-10"}]})
    so = c.post("/api/sales-orders", json={"doc_date": "2026-09-02", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 100}]}).json()
    r = c.post("/api/deliveries", json={"doc_date": "2026-09-05", "so_id": so["id"],
        "picks": [{"material_id": m, "batch": "B1", "stock_type": "NORMAL", "qty": 150}]})
    assert r.status_code == 422 and "only" in r.text


def test_order_beyond_stock_is_accepted_but_flagged(org):
    c = trading(org); m = mat(c); cu = cust(c)
    so = c.post("/api/sales-orders", json={"doc_date": "2026-09-02", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 50}]})
    assert so.status_code == 201
    assert so.json()["short"][0]["available"] == 0


# ------------------------------------------------------ stock report
def test_movements_show_in_out_and_a_running_balance(org):
    c = trading(org); m = mat(c); v = vend(c); cu = cust(c)
    p = po(c, v, m, qty=800)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-01", "po_id": p,
        "lines": [{"material_id": m, "qty": 800}]})
    so = c.post("/api/sales-orders", json={"doc_date": "2026-09-02", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 180}]}).json()
    c.post("/api/deliveries", json={"doc_date": "2026-09-05", "so_id": so["id"],
        "picks": [{"material_id": m, "stock_type": "NORMAL", "qty": 180}]})
    c.post("/api/physical", json={"doc_no": "PI1", "count_date": "2026-09-06",
        "lines": [{"material_id": m, "stock_type": "NORMAL", "counted_qty": 608}]})
    mv = c.get("/api/stock/movements").json()
    assert [x["movement"] for x in mv] == ["Goods receipt", "Goods issue", "Count adjustment"]
    assert [x["balance"] for x in mv] == [800, 620, 608]
    s = c.get("/api/stock/summary").json()[0]
    assert s["received"] == 800 and s["issued"] == 192 and s["owned"] == 608


def test_two_receipt_lines_for_one_material_raise_one_discrepancy(org):
    """Split across batches or stock types is still a single order line."""
    c = trading(org); m = mat(c, batch=True, shelf=730); v = vend(c); p = po(c, v, m, qty=800)
    r = c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-03", "po_id": p, "lines": [
        {"material_id": m, "qty": 500, "batch": "B1", "mfg_date": "2026-01-10"},
        {"material_id": m, "qty": 250, "batch": "B2", "mfg_date": "2026-05-10"}]}).json()
    assert len(r["discrepancies"]) == 1
    d = r["discrepancies"][0]
    assert d["ordered"] == 800 and d["received"] == 750 and d["difference"] == -50


def test_a_later_receipt_can_clear_the_discrepancy(org):
    c = trading(org); m = mat(c); v = vend(c); p = po(c, v, m, qty=800)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-03", "po_id": p,
        "lines": [{"material_id": m, "qty": 500}]})
    assert len(c.get("/api/discrepancies", params={"status": "HELD"}).json()) == 1
    r = c.post("/api/grn", json={"doc_no": "G2", "doc_date": "2026-09-08", "po_id": p,
        "lines": [{"material_id": m, "qty": 300}]}).json()
    assert r["discrepancies"] == []                 # 500 + 300 = the 800 ordered
    assert c.get("/api/discrepancies").json() == []
    inv = c.get("/api/discrepancies/invoiceable").json()[0]
    assert inv["delivered"] == 800 and inv["held"] == 0 and inv["invoiceable"] == 800


def test_releasing_one_line_frees_the_whole_delivered_quantity(org):
    c = trading(org); m = mat(c, batch=True, shelf=730); v = vend(c); p = po(c, v, m, qty=800)
    c.post("/api/grn", json={"doc_no": "G1", "doc_date": "2026-09-03", "po_id": p, "lines": [
        {"material_id": m, "qty": 500, "batch": "B1", "mfg_date": "2026-01-10"},
        {"material_id": m, "qty": 250, "batch": "B2", "mfg_date": "2026-05-10"}]})
    d = c.get("/api/discrepancies", params={"status": "HELD"}).json()[0]
    out = c.post(f"/api/discrepancies/{d['id']}/release").json()
    assert out["invoiceable_now"] == 750           # everything delivered, not just one batch
