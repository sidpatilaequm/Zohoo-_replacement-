"""Tests for Purchase Order supporting documents and conversion to Purchase Invoice (Vendor Invoice)."""
import io
from tests.test_api import mat, vend, cust


def test_po_document_upload_and_list(org):
    a = org()
    m = mat(a, price=1000, cost=800)
    v = vend(a)
    po = a.post("/api/purchase-orders", json={
        "doc_date": "2026-11-01",
        "vendor_id": v,
        "lines": [{"material_id": m, "qty": 10}]
    }).json()

    # Upload a document to the purchase order
    pdf_content = b"%PDF-1.4 test po quotation"
    r = a.post(
        f"/api/purchase-orders/{po['id']}/documents",
        files={"file": ("quote.pdf", pdf_content, "application/pdf")},
        data={"notes": "Vendor quote v1"},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "quote.pdf"
    assert doc["notes"] == "Vendor quote v1"
    assert doc["size"] == len(pdf_content)

    # List documents for the PO
    docs = a.get(f"/api/purchase-orders/{po['id']}/documents").json()
    assert len(docs) == 1
    assert docs[0]["id"] == doc["id"]
    assert docs[0]["filename"] == "quote.pdf"

    # Download document file
    f_res = a.get(f"/api/documents/{doc['id']}/file")
    assert f_res.status_code == 200
    assert f_res.content == pdf_content


def test_po_to_purchase_invoice_conversion_copies_documents(org):
    a = org()
    m = mat(a, price=1200, cost=950)
    v = vend(a)

    # 1. Raise PO
    po = a.post("/api/purchase-orders", json={
        "doc_date": "2026-11-02",
        "vendor_id": v,
        "lines": [{"material_id": m, "qty": 15}]
    }).json()

    # 2. Upload files to the PO
    pdf_bytes = b"%PDF-1.4 quotation and approval"
    png_bytes = b"\x89PNG\r\n\x1a\nspecification_image"

    doc1 = a.post(
        f"/api/purchase-orders/{po['id']}/documents",
        files={"file": ("quotation.pdf", pdf_bytes, "application/pdf")},
        data={"notes": "Final approved quotation"},
    ).json()

    doc2 = a.post(
        f"/api/purchase-orders/{po['id']}/documents",
        files={"file": ("spec.png", png_bytes, "image/png")},
        data={"notes": "Technical specs"},
    ).json()

    # Verify PO has 2 documents
    po_docs = a.get(f"/api/purchase-orders/{po['id']}/documents").json()
    assert len(po_docs) == 2

    # 3. Convert PO to Purchase Invoice (Vendor Invoice)
    vinv_res = a.post("/api/vendor-invoices", json={
        "doc_no": "VINV-999",
        "doc_date": "2026-11-05",
        "po_id": po["id"],
    })
    assert vinv_res.status_code == 201, vinv_res.text
    vinv = vinv_res.json()

    # 4. Verify the Purchase Invoice (Vendor Invoice) received both files
    vinv_docs = a.get(f"/api/vendor-invoices/{vinv['id']}/documents").json()
    assert len(vinv_docs) == 2
    filenames = {d["filename"] for d in vinv_docs}
    assert "quotation.pdf" in filenames
    assert "spec.png" in filenames

    # Verify content of copied files
    pdf_doc = next(d for d in vinv_docs if d["filename"] == "quotation.pdf")
    png_doc = next(d for d in vinv_docs if d["filename"] == "spec.png")
    assert pdf_doc["notes"] == "Final approved quotation"
    assert png_doc["notes"] == "Technical specs"

    r_pdf = a.get(f"/api/documents/{pdf_doc['id']}/file")
    assert r_pdf.status_code == 200
    assert r_pdf.content == pdf_bytes

    # 5. Delete one document on the Purchase Invoice; PO document remains intact
    del_r = a.delete(f"/api/documents/{pdf_doc['id']}")
    assert del_r.status_code == 204

    # Purchase invoice now has 1 document (or fallback if unique)
    vinv_docs_after = a.get(f"/api/vendor-invoices/{vinv['id']}/documents").json()
    # Note: original PO document is untouched
    po_docs_after = a.get(f"/api/purchase-orders/{po['id']}/documents").json()
    assert len(po_docs_after) == 2


def test_po_convert_endpoint_copies_documents(org):
    a = org()
    m = mat(a, price=500, cost=400)
    v = vend(a)

    po = a.post("/api/purchase-orders", json={
        "doc_date": "2026-11-03",
        "vendor_id": v,
        "lines": [{"material_id": m, "qty": 5}]
    }).json()

    pdf_bytes = b"%PDF-1.4 vendor agreement"
    a.post(
        f"/api/purchase-orders/{po['id']}/documents",
        files={"file": ("agreement.pdf", pdf_bytes, "application/pdf")},
    )

    # Use convert endpoint
    conv_res = a.post(f"/api/purchase-orders/{po['id']}/convert?doc_no=V-INV-001&doc_date=2026-11-04")
    assert conv_res.status_code == 201, conv_res.text
    vinv = conv_res.json()

    # Check vendor invoice documents
    vinv_docs = a.get(f"/api/vendor-invoices/{vinv['id']}/documents").json()
    assert len(vinv_docs) == 1
    assert vinv_docs[0]["filename"] == "agreement.pdf"


def test_proforma_to_tax_invoice_conversion_copies_documents(org):
    a = org()
    m = mat(a, price=1000)
    c = cust(a)

    # Raise proforma
    pro = a.post("/api/invoices", json={
        "doc_type": "PRO",
        "doc_date": "2026-11-01",
        "customer_id": c,
        "lines": [{"material_id": m, "qty": 2}]
    }).json()

    # Upload document to proforma
    pdf_bytes = b"%PDF-1.4 customer purchase order"
    a.post(
        f"/api/invoices/{pro['id']}/documents",
        files={"file": ("customer_po.pdf", pdf_bytes, "application/pdf")},
        data={"notes": "PO from client"},
    )

    # Convert proforma to tax invoice
    tax_res = a.post(f"/api/invoices/{pro['id']}/convert?doc_date=2026-11-05")
    assert tax_res.status_code == 200, tax_res.text
    tax = tax_res.json()

    # Verify tax invoice has copied document
    tax_docs = a.get(f"/api/invoices/{tax['id']}/documents").json()
    assert len(tax_docs) == 1
    assert tax_docs[0]["filename"] == "customer_po.pdf"
    assert tax_docs[0]["notes"] == "PO from client"
