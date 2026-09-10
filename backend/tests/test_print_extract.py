"""PDF print-outs in both layouts, and reading a vendor invoice back in."""
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from tests.test_api import mat, cust, vend


def _setup(org):
    c = org(gstin="29AABCA1234F1Z5")
    m = mat(c, code="MAT-10045", price=500, cost=450)
    cid = cust(c, state="29", gstin="29AAACE1234R1Z9")
    vid = vend(c, state="27", gstin="27AABCE1234F1Z5")
    inv = c.post("/api/invoices", json={"doc_date": "2026-09-01", "customer_id": cid,
                                        "po_no": "PO-8891", "lines": [{"material_id": m, "qty": 10}]})
    assert inv.status_code == 201, inv.text
    po = c.post("/api/purchase-orders", json={"doc_date": "2026-09-01", "vendor_id": vid,
                                              "lines": [{"material_id": m, "qty": 200, "price": 450}]})
    assert po.status_code == 201, po.text
    rc = c.post("/api/receipts", json={"pay_type": "REC", "invoice_id": inv.json()["id"],
                                       "pay_date": "2026-09-05", "amount": 2000, "mode": "NEFT",
                                       "bank_ref": "UTR123"})
    assert rc.status_code == 201, rc.text
    return c, m, inv.json(), po.json(), rc.json(), vid


def _is_pdf(r):
    return r.status_code == 200 and r.headers["content-type"] == "application/pdf" \
        and r.content[:4] == b"%PDF"


def test_prints_in_both_layouts(org):
    c, m, inv, po, rc, _ = _setup(org)
    for v in ("TRADING", "NONTRADING"):
        assert _is_pdf(c.get(f"/api/print/purchase-orders/{po['id']}.pdf?variant={v}"))
        assert _is_pdf(c.get(f"/api/print/invoices/{inv['id']}.pdf?variant={v}"))
        assert _is_pdf(c.get(f"/api/print/receipts/{rc['id']}.pdf?variant={v}"))
    r = c.get(f"/api/print/invoices/{inv['id']}.pdf?disposition=inline")
    assert _is_pdf(r) and r.headers["content-disposition"].startswith("inline")
    assert c.get(f"/api/print/invoices/{inv['id']}.pdf?variant=OTHER").status_code == 422
    assert c.get("/api/print/invoices/9999.pdf").status_code == 404


def test_default_layout_follows_company_type(org):
    c, m, inv, po, rc, _ = _setup(org)
    assert c.get("/api/print/variants").json()["default"] == "NONTRADING"
    c.put("/api/org", json={"name": "Aequm India", "company_type": "TRADING", "state_code": "29"})
    assert c.get("/api/print/variants").json()["default"] == "TRADING"
    assert _is_pdf(c.get(f"/api/print/invoices/{inv['id']}.pdf"))


def test_print_pdf_contains_the_document_numbers(org):
    import pdfplumber
    c, m, inv, po, rc, _ = _setup(org)
    r = c.get(f"/api/print/invoices/{inv['id']}.pdf?variant=TRADING")
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    assert inv["doc_no"] in text and "TAX INVOICE" in text and "HSN/SAC" in text
    assert "Bill To" in text and "Ship To" in text and "Indian Rupee" in text
    assert "Sub Total" in text and "Balance Due" in text and "Payment Made" in text
    r = c.get(f"/api/print/invoices/{inv['id']}.pdf?variant=NONTRADING")
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    assert "Terms & Conditions" in text and "Authorized Signature" in text


def test_other_tenant_cannot_print_my_documents(org):
    c, m, inv, po, rc, _ = _setup(org)
    other = org(name="Other", email="o@o.in", gstin="33AAACR9999K1Z5", state="33")
    assert other.get(f"/api/print/invoices/{inv['id']}.pdf").status_code == 404
    assert other.get(f"/api/print/purchase-orders/{po['id']}.pdf").status_code == 404


def _vendor_pdf(po_no, lines, gstin="27AABCE1234F1Z5"):
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=A4)
    y = 800
    def w(s):
        nonlocal y
        cv.drawString(40, y, s); y -= 16
    w("Example Supplies Pvt Ltd"); w(f"GSTIN {gstin}"); w("TAX INVOICE")
    w("Invoice No: SUP/2026/77    Invoice Date: 05-Sep-2026    Due Date: 05-Oct-2026")
    w(f"Buyer GSTIN 29AABCA1234F1Z5    PO No: {po_no}")
    w("# Description HSN Qty UoM Rate Amount")
    taxable = 0
    for i, (d, hsn, q, u, rate) in enumerate(lines, 1):
        w(f"{i} {d} {hsn} {q} {u} {rate:.2f} {q * rate:.2f}"); taxable += q * rate
    w(f"Taxable Value {taxable:.2f}"); w(f"IGST 18% {taxable * .18:.2f}")
    w(f"Grand Total {taxable * 1.18:.2f}")
    cv.save()
    return buf.getvalue()


def test_extracts_vendor_invoice_and_matches_masters(org):
    c, m, inv, po, rc, vid = _setup(org)
    pdf = _vendor_pdf(po["doc_no"], [("Industrial bearing MAT-10045", "998314", 200, "LIC", 450)])
    r = c.post("/api/vendor-invoices/extract", files={"file": ("sup.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["vendor_id"] == vid and d["vendor_confidence"] == 1.0
    assert d["po_id"] == po["id"]
    assert d["doc_no"] == "SUP/2026/77" and d["doc_date"] == "2026-09-05" and d["due_date"] == "2026-10-05"
    assert d["read_method"] == "text" and d["llm_used"] is False
    assert len(d["lines"]) == 1
    L = d["lines"][0]
    assert L["material_id"] == m and L["qty"] == 200 and L["price"] == 450 and L["matched_by"] == "code"
    assert abs(d["total"] - 200 * 450 * 1.18) < 1
    # the proposal records straight into the register
    r2 = c.post("/api/vendor-invoices", json={"doc_no": d["doc_no"], "doc_date": d["doc_date"],
                "due_date": d["due_date"], "po_id": d["po_id"],
                "lines": [{"material_id": L["material_id"], "qty": L["qty"], "price": L["price"]}]})
    assert r2.status_code == 201, r2.text
    assert r2.json()["variance"]["difference"] == 0


def test_extract_flags_unknown_vendor_and_line(org):
    c, m, inv, po, rc, vid = _setup(org)
    pdf = _vendor_pdf("PO/999", [("Widget assembly XL", "84821010", 3, "NOS", 1000)], gstin="33AAACZ9876Q1Z1")
    d = c.post("/api/vendor-invoices/extract", files={"file": ("x.pdf", pdf, "application/pdf")}).json()
    assert d["vendor_id"] is None and d["po_id"] is None
    assert any("Vendor not recognised" in w for w in d["warnings"])
    assert any("not found" in w for w in d["warnings"])


def test_extract_rejects_wrong_files(org):
    c, *_ = _setup(org)
    assert c.post("/api/vendor-invoices/extract",
                  files={"file": ("a.csv", b"x,y", "text/csv")}).status_code == 422
    assert c.post("/api/vendor-invoices/extract",
                  files={"file": ("a.pdf", b"", "application/pdf")}).status_code == 422
    caps = c.get("/api/vendor-invoices/extract/capabilities").json()
    assert caps["pdf_text"] is True and "ocr" in caps and "llm" in caps


def test_extract_needs_permission(org):
    c, *_ = _setup(org)
    other = org(name="Other", email="o@o.in", state="33")
    gid = [g for g in other.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    # a sales user in the other org has no 'vinv' permission
    import pytest
    r = other.api.post("/api/auth/signup", json={"name": "S", "email": "s@o.in",
        "password": "correct horse", "mode": "join", "join_tenant_id": other.tid})
    uid = [u for u in other.get("/api/users").json() if u["pending"]][0]["id"]
    other.put(f"/api/users/{uid}/role", json={"user_id": uid, "group_id": gid})
    tok = other.api.post("/api/auth/signin", json={"email": "s@o.in", "password": "correct horse"}).json()["token"]
    r = other.api.post("/api/vendor-invoices/extract", headers={"Authorization": f"Bearer {tok}",
        "X-Tenant-Id": str(other.tid)}, files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 403
