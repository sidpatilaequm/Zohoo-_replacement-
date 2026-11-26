import pytest
from datetime import date, timedelta
from decimal import Decimal


def test_e2e_po_convert_flow(org):
    c = org()

    # 1. Create a Vendor
    r_vend = c.post("/api/vendors", json={
        "code": "V-E2E-1",
        "name": "Acme Supplies Pvt Ltd",
        "party_type": "B2B",
        "addr": "Plot 10, Industrial Area, Whitefield",
        "city": "Bengaluru",
        "state_code": "29",
        "email": "supplies@acme.com",
        "payment_term_days": 30,
        "gstins": [{"gstin": "29ABCDE1234F1Z5", "is_default": True}],
    })
    assert r_vend.status_code == 201, r_vend.text
    vend_id = r_vend.json()["id"]

    # 2. Create a Material
    r_mat = c.post("/api/materials", json={
        "code": "M-E2E-1",
        "descr": "Industrial Fasteners Grade A",
        "price": 1200.0,
        "cost": 950.0,
        "hsn": "73181500",
        "stock_qty": 50,
        "uom": "BOX",
        "sgst_pct": 9,
        "cgst_pct": 9,
        "igst_pct": 18,
    })
    assert r_mat.status_code == 201, r_mat.text
    mat_id = r_mat.json()["id"]

    # 3. Create a Purchase Order
    r_po = c.post("/api/purchase-orders", json={
        "vendor_id": vend_id,
        "doc_date": "2026-11-20",
        "req_date": "2026-11-25",  # earlier than conversion date (2026-11-26)
        "subject": "Urgent procurement for Project Alpha",
        "payment_terms": "Net 30 days",
        "instructions": "Deliver to Bangalore Warehouse Gate 2",
        "lines": [
            {
                "material_id": mat_id,
                "qty": 10,
                "price": 950.0,
                "descr2": "Size M12 x 50mm high tensile",
            }
        ],
    })
    assert r_po.status_code == 201, r_po.text
    po_data = r_po.json()
    po_id = po_data["id"]
    po_doc_no = po_data["doc_no"]

    # 4. Check PO in list_pos
    pos = c.get("/api/purchase-orders").json()
    po_item = next(p for p in pos if p["id"] == po_id)
    assert po_item["status"] == "OPEN"
    assert po_item["invoiced_doc_no"] is None

    # 5. Simulate Frontend: Call convertPo without manual bill number (auto-generated)
    # Frontend calls: POST /api/purchase-orders/{id}/convert?doc_date=2026-11-26
    r_conv = c.post(f"/api/purchase-orders/{po_id}/convert?doc_date=2026-11-26")
    assert r_conv.status_code == 201, f"Conversion failed: {r_conv.status_code} {r_conv.text}"
    conv_data = r_conv.json()
    assert conv_data["id"] is not None
    assert conv_data["doc_no"] is not None
    vinv_id = conv_data["id"]
    vinv_no = conv_data["doc_no"]

    # 6. Verify PO status is now INVOICED and links to invoice
    pos_after = c.get("/api/purchase-orders").json()
    po_after = next(p for p in pos_after if p["id"] == po_id)
    assert po_after["status"] == "INVOICED"
    assert po_after["invoiced_doc_no"] == vinv_no
    assert po_after["invoiced_id"] == vinv_id

    # 7. Verify Vendor Invoice appears in list_vinv with correct lines and totals
    vinvs = c.get("/api/vendor-invoices").json()
    vinv_item = next(v for v in vinvs if v["id"] == vinv_id)
    assert vinv_item["doc_no"] == vinv_no
    assert vinv_item["po_no"] == po_doc_no
    assert vinv_item["vendor"] == "Acme Supplies Pvt Ltd"
    assert vinv_item["taxable"] == 9500.0  # 10 * 950
    assert vinv_item["total"] == 11210.0   # 9500 + 18% = 11210

    # 8. Check that duplicate conversion is rejected cleanly
    r_dup = c.post(f"/api/purchase-orders/{po_id}/convert")
    assert r_dup.status_code == 400
    assert "already been converted" in r_dup.text


def test_e2e_po_convert_via_vendor_invoice_screen(org):
    c = org()

    # 1. Vendor & Material
    r_vend = c.post("/api/vendors", json={
        "code": "V-E2E-2",
        "name": "Beta Tools Ltd",
        "party_type": "B2B",
        "addr": "Road 5, Peenya Industrial Area",
        "city": "Bengaluru",
        "state_code": "29",
        "payment_term_days": 15,
        "gstins": [{"gstin": "29BCDEF2345G2Z6", "is_default": True}],
    })
    vend_id = r_vend.json()["id"]

    r_mat = c.post("/api/materials", json={
        "code": "M-E2E-2",
        "descr": "Precision Drill Bit Set",
        "price": 2500.0,
        "cost": 1800.0,
        "hsn": "998314",
        "stock_qty": 20,
        "uom": "BOX",
        "sgst_pct": 9,
        "cgst_pct": 9,
        "igst_pct": 18,
    })
    mat_id = r_mat.json()["id"]

    # 2. PO
    r_po = c.post("/api/purchase-orders", json={
        "vendor_id": vend_id,
        "doc_date": "2026-11-15",
        "req_date": "2026-11-20",
        "lines": [{"material_id": mat_id, "qty": 4, "price": 1800.0, "descr2": "HSS Cobalt"}]
    })
    po_id = r_po.json()["id"]
    po_doc_no = r_po.json()["doc_no"]

    # 3. Simulate VendorInvoices.jsx save():
    # User selected PO in dropdown -> vendor_id is None, po_id is set, lines are sent from frontend form
    r_vi = c.post("/api/vendor-invoices", json={
        "doc_no": "BETA-INV-4412",
        "doc_date": "2026-11-26",
        "due_date": "2026-11-26",
        "po_id": po_id,
        "vendor_id": None,
        "lines": [{"material_id": mat_id, "qty": 4, "price": 1800.0, "descr2": "HSS Cobalt"}],
    })
    assert r_vi.status_code == 201, f"Failed: {r_vi.status_code} {r_vi.text}"
    vi_data = r_vi.json()
    assert vi_data["doc_no"] == "BETA-INV-4412"

    # 4. Verify PO is now INVOICED
    pos = c.get("/api/purchase-orders").json()
    po_check = next(p for p in pos if p["id"] == po_id)
    assert po_check["status"] == "INVOICED"
    assert po_check["invoiced_doc_no"] == "BETA-INV-4412"

    # 5. Verify vendor invoice list
    vinvs = c.get("/api/vendor-invoices").json()
    vi_check = next(v for v in vinvs if v["id"] == vi_data["id"])
    assert vi_check["po_no"] == po_doc_no
    assert vi_check["doc_no"] == "BETA-INV-4412"
    assert vi_check["total"] == 8496.0  # 4 * 1800 = 7200 + 18% = 8496

