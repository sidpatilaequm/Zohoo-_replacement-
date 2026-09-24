"""Editing masters, Description 2 on lines, invoice instructions, org bank fields, no stock for services."""
import io
import pdfplumber
from tests.test_api import mat, cust, vend


def _text(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_customer_vendor_material_can_be_edited(org):
    c = org(gstin="29AABCA1234F1Z5")
    cid = cust(c, state="27", gstin="27AAACE1234R1Z9")
    cur = [x for x in c.get("/api/customers").json() if x["id"] == cid][0]
    body = {"name": "Renamed Customer", "party_type": "B2B", "bill_addr": "New address", "bill_city": "Pune",
            "bill_state": "27", "bill_pin": "411001", "email": "new@x.in", "pan": "AAACE1234R",
            "gstins": [{"gstin": "27AAACE1234R1Z9", "label": "HO", "is_default": True}],
            "contacts": [{"first_name": "Anita", "phone": "9845012345"}]}
    r = c.put(f"/api/customers/{cid}", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "Renamed Customer" and d["code"] == cur["code"] and d["contacts"][0]["first_name"] == "Anita"
    assert c.put("/api/customers/9999", json=body).status_code == 404
    vid = vend(c, state="29", gstin="29AAACR1234K1Z5")
    r = c.put(f"/api/vendors/{vid}", json={"name": "Vendor Two", "party_type": "B2B", "addr": "A", "city": "B",
        "state_code": "29", "gstins": [{"gstin": "29AAACR1234K1Z5"}], "contacts": []})
    assert r.status_code == 200 and r.json()["name"] == "Vendor Two"
    m = mat(c, code="MAT-1", price=100, cost=80)
    r = c.put(f"/api/materials/{m}", json={"code": "MAT-1", "descr": "Better name", "price": 150, "cost": 90,
        "hsn": "998314", "uom": "NOS", "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18, "use_hsn_rates": False})
    assert r.status_code == 200, r.text
    assert r.json()["descr"] == "Better name" and r.json()["price"] == 150
    # two materials cannot share a code
    m2 = mat(c, code="MAT-2", price=1, cost=1)
    assert c.put(f"/api/materials/{m2}", json={"code": "MAT-1", "descr": "x", "price": 1, "hsn": "998314",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18, "use_hsn_rates": False}).status_code == 409


def test_description2_saved_on_line_and_printed_after_description(org):
    c = org(gstin="29AABCA1234F1Z5")
    m = mat(c, code="MSO-1", price=1400, cost=1000)
    cid = cust(c, state="27", gstin="27ACCFA0369A1Z0")
    vid = vend(c, state="29", gstin="29AAACR1234K1Z5")
    r = c.post("/api/invoices", json={"doc_date": "2026-06-30", "customer_id": cid, "subject": "Microsoft office",
        "instructions": "Thanks for your business. Pay immediately.",
        "lines": [{"material_id": m, "qty": 10, "descr2": "basic plan"},
                  {"material_id": m, "qty": 6, "price": 1000, "descr2": "basic plan migration"}]})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    d = c.get(f"/api/invoices/{iid}").json()
    assert d["subject"] == "Microsoft office" and d["instructions"].startswith("Thanks")
    descrs = [l["descr"] for l in d["totals"]["lines"]]
    assert descrs[0].endswith(" basic plan") and descrs[1].endswith(" basic plan migration")
    # the material master itself is untouched
    assert [x for x in c.get("/api/materials").json() if x["id"] == m][0]["descr"] == "MSO-1"
    text = _text(c.get(f"/api/print/invoices/{iid}.pdf").content)
    assert "basic plan migration" in text and "Microsoft office" in text and "Pay immediately" in text
    assert "Sub Total 20,000.00" in text and "IGST18 (18%) 3,600.00" in text and "23,600.00" in text
    assert "Twenty Three Thousand Six Hundred" in text
    # purchase side: PO line keeps its own Description 2 and prints it
    r = c.post("/api/purchase-orders", json={"doc_date": "2026-06-30", "vendor_id": vid,
        "lines": [{"material_id": m, "qty": 5, "price": 900, "descr2": "for project X"}]})
    assert r.status_code == 201, r.text
    po = r.json()
    assert "for project X" in _text(c.get(f"/api/print/purchase-orders/{po['id']}.pdf").content)
    r = c.post("/api/vendor-invoices", json={"doc_no": "V/9", "doc_date": "2026-07-01", "po_id": po["id"]})
    assert r.status_code == 201, r.text          # lines (with descr2) copied from the PO
    r = c.post("/api/vendor-invoices", json={"doc_no": "V/10", "doc_date": "2026-07-01", "vendor_id": vid,
        "lines": [{"material_id": m, "qty": 1, "price": 5, "descr2": "spare"}]})
    assert r.status_code == 201, r.text


def test_org_bank_details_print_in_terms(org):
    c = org(gstin="29AABCA1234F1Z5")
    r = c.put("/api/org", json={"name": "Aequm India Private Limited", "gstin": "29AABCA1234F1Z5", "state_code": "29",
        "bank_name": "SBI", "bank_ifsc": "SBIN0040807", "bank_account": "38600386525"})
    assert r.status_code == 200 and r.json()["bank_ifsc"] == "SBIN0040807"
    m = mat(c); cid = cust(c, state="29", gstin="29AAACE1234R1Z9")
    iid = c.post("/api/invoices", json={"doc_date": "2026-06-30", "customer_id": cid,
                                        "lines": [{"material_id": m, "qty": 1}]}).json()["id"]
    text = _text(c.get(f"/api/print/invoices/{iid}.pdf").content)
    assert "Aequm India Private Limited, SBI Account No: 38600386525 IFSC Code:" in text and "SBIN0040807" in text
    assert "Terms & Conditions" in text


def test_services_company_never_touches_stock(org):
    c = org()                                   # NONTRADING by default
    m = mat(c, stock=0); cid = cust(c); vid = vend(c, state="29", gstin="29AAACR1234K1Z5")
    r = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cid,
                                      "lines": [{"material_id": m, "qty": 500}]})
    assert r.status_code == 201, r.text          # no "exceeds stock" for a services company
    assert c.get("/api/materials").json()[0]["stock_qty"] == 0
    r = c.post("/api/vendor-invoices", json={"doc_no": "V/1", "doc_date": "2026-08-11", "vendor_id": vid,
                                             "lines": [{"material_id": m, "qty": 20, "price": 5}]})
    assert r.status_code == 201, r.text
    assert c.get("/api/materials").json()[0]["stock_qty"] == 0
    iid = r.json()["id"]
