"""Tests for proforma reconvert/override and purchase order edit/delete/descr2."""
from decimal import Decimal


def mat(c, code="MAT-001", price=1000, cost=800, stock=100):
    r = c.post("/api/materials", json={
        "code": code, "descr": f"Material {code}", "price": price,
        "cost": cost, "hsn": "998314", "stock_qty": stock, "uom": "LIC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def cust(c, code="CUST-001", state="29", gstin="29AAACE1234R1Z9"):
    r = c.post("/api/customers", json={
        "code": code, "name": f"Customer {code}", "party_type": "B2B",
        "bill_addr": "123 Main St", "bill_city": "Bangalore", "bill_state": state,
        "gstins": [{"gstin": gstin, "is_default": True}]
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def vend(c, code="VEND-001", state="29", gstin="29BBBCE1234R1Z8"):
    r = c.post("/api/vendors", json={
        "code": code, "name": f"Vendor {code}", "party_type": "B2B",
        "addr": "456 Vendor Way", "city": "Bangalore", "state_code": state,
        "gstins": [{"gstin": gstin, "is_default": True}]
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_proforma_reconvert_overrides_existing_invoice(org):
    c = org()
    cid = cust(c, "C001")
    mid1 = mat(c, "M001", price=1000)
    mid2 = mat(c, "M002", price=2000)

    # 1. Create a proforma
    r_pro = c.post("/api/invoices", json={
        "doc_type": "PRO", "doc_date": "2026-08-10", "customer_id": cid,
        "lines": [{"material_id": mid1, "qty": 2, "price": 1000, "descr2": "initial term"}]
    })
    assert r_pro.status_code == 201
    pro = r_pro.json()
    pro_id = pro["id"]

    # 2. Convert to tax invoice
    r_conv = c.post(f"/api/invoices/{pro_id}/convert?doc_date=2026-08-15")
    assert r_conv.status_code == 200
    tax = r_conv.json()
    tax_id = tax["id"]
    tax_no = tax["doc_no"]
    assert tax["totals"]["rounded"] == 2360.0

    # 3. Converting again without override raises 409
    r_dup = c.post(f"/api/invoices/{pro_id}/convert")
    assert r_dup.status_code == 409

    # 4. Edit the proforma: change qty and add a second line
    r_edit = c.put(f"/api/invoices/{pro_id}", json={
        "doc_type": "PRO", "doc_date": "2026-08-10", "customer_id": cid,
        "lines": [
            {"material_id": mid1, "qty": 3, "price": 1000, "descr2": "revised term"},
            {"material_id": mid2, "qty": 1, "price": 2000, "descr2": "add-on pack"},
        ]
    })
    assert r_edit.status_code == 200

    # 5. Reconvert with override=true -> overrides existing tax invoice
    r_reconv = c.post(f"/api/invoices/{pro_id}/convert?override=true")
    assert r_reconv.status_code == 200
    reconv_data = r_reconv.json()
    assert reconv_data["id"] == tax_id
    assert reconv_data["doc_no"] == tax_no
    # 3*1000 + 1*2000 = 5000 + 18% GST (900) = 5900.0
    assert reconv_data["totals"]["rounded"] == 5900.0

    # Verify the tax invoice has updated lines in get_invoice
    tax_fetched = c.get(f"/api/invoices/{tax_id}").json()
    lines = tax_fetched["invoice"]["lines"]
    assert len(lines) == 2
    assert lines[0]["qty"] == 3.0
    assert lines[0]["descr2"] == "revised term"
    assert lines[1]["qty"] == 1.0
    assert lines[1]["descr2"] == "add-on pack"


def test_proforma_reconvert_blocked_if_receipts_recorded(org):
    c = org()
    cid = cust(c, "C002")
    mid = mat(c, "M003", price=1000)

    # Create & convert
    pro = c.post("/api/invoices", json={
        "doc_type": "PRO", "doc_date": "2026-08-10", "customer_id": cid,
        "lines": [{"material_id": mid, "qty": 1, "price": 1000}]
    }).json()
    tax = c.post(f"/api/invoices/{pro['id']}/convert").json()

    # Record receipt against tax invoice
    r_rec = c.post("/api/receipts", json={
        "pay_type": "REC", "pay_date": "2026-08-12", "invoice_id": tax["id"],
        "amount": 1180, "tds": 0, "mode": "NEFT"
    })
    assert r_rec.status_code == 201

    # Attempt to reconvert / override -> 409
    r_bad = c.post(f"/api/invoices/{pro['id']}/convert?override=true")
    assert r_bad.status_code == 409
    assert "receipts" in r_bad.text


def test_purchase_order_crud_and_descr2(org):
    c = org()
    vid = vend(c, "V001")
    mid1 = mat(c, "MP01", price=500, cost=400)
    mid2 = mat(c, "MP02", price=800, cost=650)

    # 1. Create Purchase Order with descr2
    r_po = c.post("/api/purchase-orders", json={
        "vendor_id": vid, "doc_date": "2026-08-01", "req_date": "2026-08-10",
        "lines": [
            {"material_id": mid1, "qty": 10, "price": 400, "descr2": "batch A-1"},
            {"material_id": mid2, "qty": 5, "price": 650, "descr2": "urgent dispatch"},
        ]
    })
    assert r_po.status_code == 201
    po = r_po.json()
    poid = po["id"]

    # 2. Get PO details and check descr2
    fetched = c.get(f"/api/purchase-orders/{poid}").json()
    assert fetched["vendor"] == "Vendor V001"
    assert len(fetched["lines"]) == 2
    assert fetched["lines"][0]["descr2"] == "batch A-1"
    assert fetched["lines"][1]["descr2"] == "urgent dispatch"

    # 3. Update Purchase Order (edit lines & dates)
    r_up = c.put(f"/api/purchase-orders/{poid}", json={
        "vendor_id": vid, "doc_date": "2026-08-02", "req_date": "2026-08-12",
        "lines": [
            {"material_id": mid1, "qty": 12, "price": 390, "descr2": "batch A-1 revised"},
        ]
    })
    assert r_up.status_code == 200
    up = c.get(f"/api/purchase-orders/{poid}").json()
    assert str(up["doc_date"]) == "2026-08-02"
    assert len(up["lines"]) == 1
    assert up["lines"][0]["qty"] == 12.0
    assert up["lines"][0]["price"] == 390.0
    assert up["lines"][0]["descr2"] == "batch A-1 revised"

    # 4. Delete Purchase Order
    r_del = c.delete(f"/api/purchase-orders/{poid}")
    assert r_del.status_code == 204

    # 5. Check no longer exists
    assert c.get(f"/api/purchase-orders/{poid}").status_code == 404


def test_delete_po_blocked_when_invoiced(org):
    c = org()
    vid = vend(c, "V002")
    mid = mat(c, "MP03", price=1000, cost=800)

    po = c.post("/api/purchase-orders", json={
        "vendor_id": vid, "doc_date": "2026-08-05",
        "lines": [{"material_id": mid, "qty": 4, "price": 800}]
    }).json()

    # Raise vendor invoice against PO
    r_vi = c.post("/api/vendor-invoices", json={
        "vendor_id": vid, "doc_no": "VINV-999", "doc_date": "2026-08-06",
        "po_id": po["id"]
    })
    assert r_vi.status_code == 201

    # Attempt delete PO -> 409
    r_del = c.delete(f"/api/purchase-orders/{po['id']}")
    assert r_del.status_code == 409
