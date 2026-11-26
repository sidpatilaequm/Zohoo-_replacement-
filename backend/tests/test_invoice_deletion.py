"""Tests for invoice deletion and historical archiving."""
from decimal import Decimal


def mat(c, code="MAT-001", price=1000, stock=100):
    r = c.post("/api/materials", json={
        "code": code, "descr": f"Material {code}", "price": price,
        "cost": price * 0.8, "hsn": "998314", "stock_qty": stock, "uom": "LIC",
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


def test_delete_tax_invoice_saves_history(org):
    c = org()
    cid = cust(c, "C001")
    mid = mat(c, "M001", price=1000)

    # 1. Create a tax invoice
    r_inv = c.post("/api/invoices", json={
        "doc_type": "TAX", "doc_date": "2026-08-10", "customer_id": cid,
        "lines": [{"material_id": mid, "qty": 5, "price": 1000}]
    })
    assert r_inv.status_code == 201, r_inv.text
    inv = r_inv.json()
    inv_id = inv["id"]
    doc_no = inv["doc_no"]

    # Verify invoice is in active register
    active = c.get("/api/invoices?type=TAX").json()
    assert any(x["id"] == inv_id for x in active)

    # 2. Delete invoice without sufficient reason -> 422
    r_bad = c.delete(f"/api/invoices/{inv_id}?reason=no")
    assert r_bad.status_code == 422

    # 3. Delete invoice with valid reason -> 204
    r_del = c.delete(f"/api/invoices/{inv_id}?reason=Duplicate client order entry")
    assert r_del.status_code == 204

    # Verify it is no longer in active invoices
    active_after = c.get("/api/invoices?type=TAX").json()
    assert not any(x["id"] == inv_id for x in active_after)

    # 4. Verify it is present in deleted invoices history
    deleted_history = c.get("/api/invoices/deleted?doc_type=TAX").json()
    assert len(deleted_history) >= 1
    found = [d for d in deleted_history if d["doc_no"] == doc_no][0]
    assert found["customer"] == "Customer C001"
    assert found["taxable"] == 5000.0
    assert found["reason"] == "Duplicate client order entry"
    assert found["deleted_by"] == "Admin"
    assert found["snapshot"] is not None
    assert len(found["snapshot"]["lines"]) == 1
    assert found["snapshot"]["lines"][0]["material_code"] == "M001"
    assert found["snapshot"]["lines"][0]["qty"] == 5.0

    # 5. Check detail endpoint
    detail = c.get(f"/api/invoices/deleted/{found['id']}").json()
    assert detail["doc_no"] == doc_no
    assert detail["snapshot"]["totals"]["taxable"] == 5000.0


def test_delete_proforma_saves_history(org):
    c = org()
    cid = cust(c, "C002", state="33", gstin="33AAACE1234R1Z9")
    mid = mat(c, "M002", price=500)

    pro = c.post("/api/invoices", json={
        "doc_type": "PRO", "doc_date": "2026-08-11", "customer_id": cid,
        "lines": [{"material_id": mid, "qty": 2, "price": 500}]
    }).json()

    # Delete proforma
    r = c.delete(f"/api/invoices/{pro['id']}?reason=Customer requested quotation change")
    assert r.status_code == 204

    # Verify present in deleted history under PRO
    deleted = c.get("/api/invoices/deleted?doc_type=PRO").json()
    found = [d for d in deleted if d["doc_no"] == pro["doc_no"]][0]
    assert found["doc_type"] == "PRO"
    assert found["customer"] == "Customer C002"
    assert found["total"] == 1180.0
    assert found["reason"] == "Customer requested quotation change"


def test_delete_blocked_when_receipts_exist(org):
    c = org()
    cid = cust(c, "C003")
    mid = mat(c, "M003", price=2000)

    inv = c.post("/api/invoices", json={
        "doc_type": "TAX", "doc_date": "2026-08-12", "customer_id": cid,
        "lines": [{"material_id": mid, "qty": 1, "price": 2000}]
    }).json()

    # Record receipt against invoice
    r_pay = c.post("/api/receipts", json={
        "pay_type": "REC", "pay_date": "2026-08-15", "invoice_id": inv["id"],
        "amount": 2360, "tds": 0, "mode": "NEFT"
    })
    assert r_pay.status_code == 201

    # Attempt delete -> 409
    r = c.delete(f"/api/invoices/{inv['id']}?reason=Attempt delete with receipts")
    assert r.status_code == 409
    assert "receipts" in r.text


def test_deleted_invoices_accessible_with_saved_permission(api, org):
    a = org(name="One", email="admin@x.co")
    cid = cust(a, "C004")
    mid = mat(a, "M004", price=1000)
    inv = a.post("/api/invoices", json={
        "doc_type": "TAX", "doc_date": "2026-08-10", "customer_id": cid,
        "lines": [{"material_id": mid, "qty": 1, "price": 1000}]
    }).json()
    r_del = a.delete(f"/api/invoices/{inv['id']}?reason=Testing saved role access")
    assert r_del.status_code == 204

    # Create a custom group that only has "saved" permission
    r_grp = a.post("/api/groups", json={"name": "Invoice Viewer", "perms": ["saved"]})
    assert r_grp.status_code == 201, r_grp.text
    gid = r_grp.json()["id"]

    a.post("/api/users", json={"name": "Viewer", "email": "v@x.co",
        "password": "correct horse", "group_id": gid})
    tok = api.post("/api/auth/signin", json={"email": "v@x.co",
        "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(a.tid)}

    # User with 'saved' permission can list deleted invoices without 403
    r = api.get("/api/invoices/deleted?doc_type=TAX", headers=h)
    assert r.status_code == 200, r.text
    items = r.json()
    assert any(x["doc_no"] == inv["doc_no"] for x in items)

    # And view deleted invoice details
    did = [x["id"] for x in items if x["doc_no"] == inv["doc_no"]][0]
    r_det = api.get(f"/api/invoices/deleted/{did}", headers=h)
    assert r_det.status_code == 200, r_det.text

