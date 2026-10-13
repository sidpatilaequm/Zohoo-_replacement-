"""v4.4 — proforma number range and register, conversion that keeps the proforma,
QR code, notes and terms on the print-out, and e-mailing documents over SMTP."""
import base64, email, io
import pytest
from .test_api import mat, cust, vend

ORG = {"name": "Aequm India Private Limited", "state_code": "29",
       "bank_name": "SBI", "bank_account": "38600386525", "bank_ifsc": "SBIN0040807"}


def _setup(org, **extra):
    a = org(name="Aequm India Private Limited")
    r = a.put("/api/org", json={**ORG, **extra})
    assert r.status_code == 200, r.text
    m, c = mat(a), cust(a)
    a.put(f"/api/customers/{c}", json={**a.get("/api/customers").json()[0],
                                         "email": "accounts@customer.in"})
    return a, m, c


def _inv(a, m, c, doc_type="TAX", date="2026-10-01", **kw):
    r = a.post("/api/invoices", json={"doc_date": date, "doc_type": doc_type, "customer_id": c,
                                      "lines": [{"material_id": m, "qty": 2}], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _pdf_text(a, iid, extra=""):
    import pdfplumber
    r = a.get(f"/api/print/invoices/{iid}.pdf{extra}")
    assert r.status_code == 200, r.text
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages), r.content


# ------------------------------------------------------- number ranges
def test_proforma_has_its_own_number_range(org):
    a, m, c = _setup(org)
    assert _inv(a, m, c, "PRO")["doc_no"] == "PI/001"
    assert _inv(a, m, c, "TAX")["doc_no"] == "INV/001"
    assert _inv(a, m, c, "PRO")["doc_no"] == "PI/002"
    assert _inv(a, m, c, "TAX")["doc_no"] == "INV/002"


def test_proforma_range_is_set_in_company_information(org):
    a, m, c = _setup(org, pro_prefix="AEQ-PI/", pro_seq=41)
    o = a.get("/api/org").json()
    assert o["pro_prefix"] == "AEQ-PI/" and o["pro_seq"] == 41
    assert a.get("/api/invoices/next-no?doc_type=PRO").json()["doc_no"] == "AEQ-PI/041"
    assert _inv(a, m, c, "PRO")["doc_no"] == "AEQ-PI/041"
    assert a.get("/api/org").json()["pro_seq"] == 42
    # the preview does not use a number up
    assert a.get("/api/invoices/next-no?doc_type=TAX").json()["doc_no"] == "INV/001"
    assert _inv(a, m, c, "TAX")["doc_no"] == "INV/001"


def test_proforma_range_with_financial_year(org):
    a, m, c = _setup(org, pro_fy=True, fy_start_month=4, fy_start_day=1)
    assert _inv(a, m, c, "PRO", date="2026-10-01")["doc_no"] == "PI/2026-27/001"
    assert _inv(a, m, c, "PRO", date="2027-04-02")["doc_no"] == "PI/2027-28/001"


def test_proforma_prefix_cannot_equal_invoice_prefix(org):
    a = org()
    r = a.put("/api/org", json={**ORG, "inv_prefix": "INV/", "pro_prefix": "INV/"})
    assert r.status_code == 422 and "must differ" in r.text


# ------------------------------------------------------- conversion
def test_converting_keeps_the_proforma_and_raises_a_new_tax_invoice(org):
    a, m, c = _setup(org)
    pro = _inv(a, m, c, "PRO")
    r = a.post(f"/api/invoices/{pro['id']}/convert?doc_date=2026-10-05")
    assert r.status_code == 200, r.text
    tax = r.json()
    assert tax["id"] != pro["id"] and tax["doc_no"] == "INV/001"
    assert tax["converted_from"] == "PI/001" and tax["totals"]["rounded"] == pro["totals"]["rounded"]

    pros = a.get("/api/invoices?doc_type=PRO").json()
    assert [p["doc_no"] for p in pros] == ["PI/001"]
    assert pros[0]["doc_type"] == "PRO" and pros[0]["converted_to"] == "INV/001"
    assert pros[0]["converted_to_id"] == tax["id"]
    taxes = a.get("/api/invoices?doc_type=TAX").json()
    assert [t["doc_no"] for t in taxes] == ["INV/001"] and taxes[0]["converted_from"] == "PI/001"
    assert str(taxes[0]["doc_date"]) == "2026-10-05"

    # once only, and the proforma is kept as the record
    assert a.post(f"/api/invoices/{pro['id']}/convert").status_code == 409
    assert a.delete(f"/api/invoices/{pro['id']}").status_code == 409

    # the copy still prints as a proforma, and points at its tax invoice
    text, _ = _pdf_text(a, pro["id"])
    assert "PROFORMA INVOICE" in text and "INV/001" in text
    text, _ = _pdf_text(a, tax["id"])
    assert "TAX INVOICE" in text and "PI/001" in text


def test_deleting_the_tax_invoice_frees_the_proforma(org):
    a, m, c = _setup(org)
    pro = _inv(a, m, c, "PRO")
    tax = a.post(f"/api/invoices/{pro['id']}/convert").json()
    assert a.delete(f"/api/invoices/{tax['id']}").status_code == 204
    p = a.get("/api/invoices?doc_type=PRO").json()[0]
    assert p["converted_to"] is None
    assert a.post(f"/api/invoices/{pro['id']}/convert").status_code == 200


def test_conversion_moves_stock_once_for_a_trading_company(org):
    a = org(trading=True); m = mat(a, stock=100); c = cust(a)
    pro = _inv(a, m, c, "PRO")
    a.post(f"/api/invoices/{pro['id']}/convert")
    assert a.get("/api/materials").json()[0]["stock_qty"] == 98


def test_converted_proforma_stays_out_of_gst(org):
    a, m, c = _setup(org)
    pro = _inv(a, m, c, "PRO", date="2026-10-01")
    a.post(f"/api/invoices/{pro['id']}/convert?doc_date=2026-10-02")
    g = a.get("/api/returns/gstr1", params={"period": "2026-10"}).json()
    assert g["totals"]["taxable"] == 2500.0          # the tax invoice only, not twice


# ------------------------------------------------------- registers and access
def test_a_group_without_proforma_sees_only_tax_invoices(api, org):
    a, m, c = _setup(org)
    _inv(a, m, c, "PRO"); _inv(a, m, c, "TAX")
    r = a.post("/api/groups", json={"name": "Billing", "perms": ["saved"]})
    assert r.status_code == 201, r.text
    a.post("/api/users", json={"name": "B", "email": "b@x.co", "password": "correct horse",
                               "group_id": r.json()["id"]})
    tok = api.post("/api/auth/signin", json={"email": "b@x.co",
                                              "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(a.tid)}
    rows = api.get("/api/invoices", headers=h).json()
    assert {x["doc_type"] for x in rows} == {"TAX"}
    assert api.get("/api/invoices?doc_type=PRO", headers=h).status_code == 403


def test_default_groups_carry_the_proforma_register(org):
    a = org()
    for g in a.get("/api/groups").json():
        if "saved" in g["perms"]:
            assert "proforma" in g["perms"], g["name"]


# ------------------------------------------------------- print-out
def test_proforma_prints_proforma_heading_notes_terms_and_bank(org):
    a, m, c = _setup(org)
    pro = _inv(a, m, c, "PRO")
    text, _ = _pdf_text(a, pro["id"])
    flat = " ".join(text.split())
    assert "PROFORMA INVOICE" in flat and "TAX INVOICE" not in flat
    assert "Proforma Date" in flat
    assert "Thanks for your business. Pay immediately." in flat
    assert "Terms & Conditions" in flat
    assert "Pay immediately for license activation" in flat
    import pdfplumber
    _, raw = _pdf_text(a, pro["id"])
    with pdfplumber.open(io.BytesIO(raw)) as pdf:        # the left (notes and terms) column
        pg = pdf.pages[0]
        left = " ".join(pg.crop((0, 0, pg.width * 0.55, pg.height)).extract_text().split())
    assert ("Aequm India Private Limited, SBI Account No: 38600386525 "
            "IFSC Code: SBIN0040807") in left


def test_tax_invoice_prints_tax_heading_and_the_same_notes(org):
    a, m, c = _setup(org)
    inv = _inv(a, m, c, "TAX", instructions="PO reference must be quoted.")
    flat = " ".join(_pdf_text(a, inv["id"])[0].split())
    assert "TAX INVOICE" in flat and "PROFORMA" not in flat
    assert "Thanks for your business. Pay immediately." in flat
    assert "PO reference must be quoted." in flat           # the invoice's own note too
    assert "Pay immediately for license activation" in flat


def test_notes_and_terms_follow_company_information(org):
    a, m, c = _setup(org, inv_notes="Line one\nLine two", inv_terms="")
    flat = " ".join(_pdf_text(a, _inv(a, m, c)["id"])[0].split())
    assert "Line one" in flat and "Line two" in flat
    assert "license activation" not in flat
    assert "38600386525" in flat                             # bank line still prints


def test_every_invoice_carries_a_qr_code_with_its_details(org):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    pdfium = pytest.importorskip("pypdfium2")
    a, m, c = _setup(org)
    for dt in ("PRO", "TAX"):
        d = _inv(a, m, c, dt)
        _, raw = _pdf_text(a, d["id"])
        page = pdfium.PdfDocument(raw)[0]
        data = ""
        for scale in (4, 5, 6):          # roughly 300-430 dpi, as printed
            img = np.array(page.render(scale=scale).to_pil().convert("RGB"))
            data = cv2.QRCodeDetector().detectAndDecode(img)[0]
            if data:
                break
        assert data, f"no QR found on the {dt} print-out"
        assert ("PROFORMA INVOICE" if dt == "PRO" else "TAX INVOICE") in data
        assert d["doc_no"] in data and "Aequm India Private Limited" in data
        assert "33AABCK1234M1Z8" in data                     # buyer GSTIN
        assert "Total: INR 2,950.00" in data
        assert "A/c 38600386525" in data and "SBIN0040807" in data


# ------------------------------------------------------- e-mail
@pytest.fixture
def outbox(monkeypatch):
    sent = []
    from app import mailer

    def fake(t, msg):
        sent.append({"msg": msg, "rcpt": mailer.recipients(msg), "host": t.smtp_host})
        return {}
    monkeypatch.setattr(mailer, "deliver", fake)
    return sent


def _smtp(a):
    r = a.put("/api/org/smtp", json={"from_name": "Aequm Accounts",
                                     "from_email": "accounts@aequm.in", "host": "smtp.test",
                                     "port": 587, "encryption": "STARTTLS",
                                     "username": "accounts@aequm.in", "password": "pw",
                                     "bcc": "archive@aequm.in"})
    assert r.status_code == 200, r.text


def test_draft_is_prefilled_for_a_proforma(org):
    a, m, c = _setup(org)
    _smtp(a)
    pro = _inv(a, m, c, "PRO")
    d = a.get(f"/api/email/draft?kind=invoice&id={pro['id']}").json()
    assert d["doc_label"] == "Proforma Invoice" and d["smtp_ready"]
    assert d["from"] == "Aequm Accounts <accounts@aequm.in>"
    assert d["to"] == ["accounts@customer.in"] and d["bcc"] == ["archive@aequm.in"]
    assert d["subject"] == "Proforma Invoice PI/001 from Aequm India Private Limited"
    assert "PI/001" in d["body"] and "Thanks for your business" in d["body"]
    assert "38600386525" in d["body"]
    assert d["attachment"] == "PI-001.pdf"


def test_send_attaches_the_pdf_and_logs_it(org, outbox):
    a, m, c = _setup(org)
    _smtp(a)
    inv = _inv(a, m, c, "TAX")
    extra = base64.b64encode(b"hello").decode()
    r = a.post("/api/email/send", json={
        "kind": "invoice", "id": inv["id"], "to": ["accounts@customer.in"],
        "cc": ["cfo@customer.in"], "bcc": ["archive@aequm.in"],
        "subject": "Your invoice", "body": "Please find attached.",
        "extra": [{"filename": "note.txt", "content_base64": extra, "content_type": "text/plain"}]})
    assert r.status_code == 200, r.text
    assert r.json()["attachments"] == ["INV-001.pdf", "note.txt"]
    msg = outbox[0]["msg"]
    assert msg["From"] == "Aequm Accounts <accounts@aequm.in>"
    assert msg["To"] == "accounts@customer.in" and msg["Cc"] == "cfo@customer.in"
    assert msg["Bcc"] is None                                # never in the headers
    assert outbox[0]["rcpt"] == ["accounts@customer.in", "cfo@customer.in", "archive@aequm.in"]
    parsed = email.message_from_bytes(msg.as_bytes())
    files = {p.get_filename(): p.get_payload(decode=True)
             for p in parsed.walk() if p.get_filename()}
    assert files["INV-001.pdf"].startswith(b"%PDF") and files["note.txt"] == b"hello"
    log = a.get(f"/api/email/log?kind=invoice&id={inv['id']}").json()
    assert log[0]["status"] == "SENT" and log[0]["to"] == "accounts@customer.in"


def test_purchase_order_can_be_emailed_to_the_vendor(org, outbox):
    a, m, c = _setup(org)
    _smtp(a)
    v = vend(a)
    po = a.post("/api/purchase-orders", json={"doc_date": "2026-10-01", "vendor_id": v,
                                              "lines": [{"material_id": m, "qty": 1}]}).json()
    d = a.get(f"/api/email/draft?kind=po&id={po['id']}").json()
    assert d["doc_label"] == "Purchase Order" and d["attachment"] == "PO-001.pdf"
    assert d["subject"].startswith("Purchase Order PO/001")
    r = a.post("/api/email/send", json={"kind": "po", "id": po["id"], "to": ["sales@vendor.in"],
                                         "subject": d["subject"], "body": d["body"]})
    assert r.status_code == 200, r.text
    assert r.json()["attachments"] == ["PO-001.pdf"]


def test_send_without_smtp_explains_and_is_logged_as_failed(org):
    a, m, c = _setup(org)
    inv = _inv(a, m, c)
    r = a.post("/api/email/send", json={"kind": "invoice", "id": inv["id"],
                                         "to": ["x@y.in"], "subject": "s", "body": "b"})
    assert r.status_code == 502 and "Email and SMTP" in r.text
    assert a.get(f"/api/email/log?kind=invoice&id={inv['id']}").json()[0]["status"] == "FAILED"


def test_bad_addresses_are_refused_before_sending(org, outbox):
    a, m, c = _setup(org)
    _smtp(a)
    inv = _inv(a, m, c)
    r = a.post("/api/email/send", json={"kind": "invoice", "id": inv["id"],
                                         "to": ["not-an-address"], "subject": "s", "body": "b"})
    assert r.status_code == 422 and outbox == []


def test_smtp_test_mail(org, outbox):
    a = org()
    _smtp(a)
    r = a.post("/api/org/smtp/test", json={"to": "me@aequm.in"})
    assert r.status_code == 200, r.text
    assert outbox[0]["rcpt"] == ["me@aequm.in"] and outbox[0]["host"] == "smtp.test"
